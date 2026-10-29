"""Run one QLoRA forward/backward step for Qwen3.5-4B on a Modal L40S.

Run from the repository root:

    $env:HTTP_PROXY = ""
    $env:HTTPS_PROXY = ""
    $env:ALL_PROXY = ""
    .\model\training\.venv-modal\Scripts\modal.exe run model\training\code\training\modal_qwen4b_smoke.py

The smoke test deliberately uses one image and a 15-minute function timeout.
It saves only a small LoRA adapter plus runtime metrics to ``uveitis-runs``.
"""

from __future__ import annotations

import json
import csv
import time
from datetime import UTC, datetime
from pathlib import Path

import modal

from modal_volumes import (
    DATA_VOLUME_NAME,
    MANIFEST_PATH,
    MODELS_VOLUME_NAME,
    QWEN4B_SUBDIR,
    RUNS_VOLUME_NAME,
    data_volume,
    models_volume,
    runs_volume,
)


APP_NAME = "uveitis-qwen4b-smoke"
MODEL_PATH = f"/models/{QWEN4B_SUBDIR}"
TRANSFORMERS_COMMIT = "50e35cc0ca18ec19b80653690de553e6decf74f5"
PEFT_COMMIT = "7d6315ae910bf62b6044a7ca917bccf5881f5e43"
RUN_ID = "qwen4b-smoke-20261025-02"
RUN_ROOT = f"/runs/qwen3.5-4b/{RUN_ID}"
MAX_PIXELS = 448 * 448
MAX_LENGTH = 1024

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git")
    .pip_install(
        "torch==2.8.0",
        "torchvision==0.23.0",
        f"transformers @ git+https://github.com/huggingface/transformers.git@{TRANSFORMERS_COMMIT}",
        "accelerate==1.10.1",
        f"peft @ git+https://github.com/huggingface/peft.git@{PEFT_COMMIT}",
        "bitsandbytes==0.47.0",
        "Pillow==11.3.0",
        "sentencepiece==0.2.1",
        "numpy==1.26.4",
    )
    .add_local_file(
        Path(__file__).with_name("modal_volumes.py"),
        remote_path="/root/modal_volumes.py",
        copy=True,
    )
)

app = modal.App(APP_NAME)


def _encode_example(processor, image, task: str, label: str) -> dict:
    allowed = {
        "oct_uveitis_4class": [
            "Intermediate+Posterior Uveitis",
            "Normal",
            "Panuveitis",
            "RRD-PVR",
        ],
        "oct_aux_4class": ["CNV", "DME", "DRUSEN", "NORMAL"],
    }[task]
    prompt = (
        "Classify this retina image for the stated task. "
        f"Task: {task}. Allowed labels: {json.dumps(allowed)}. "
        "Use exactly one allowed label. Return only JSON with "
        '{"label":"...","requires_human_review":true}.'
    )
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": prompt},
            ],
        }
    ]
    prompt_text = processor.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )
    answer = json.dumps(
        {"label": label, "requires_human_review": True},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    full_messages = messages + [{"role": "assistant", "content": answer}]
    full_text = processor.apply_chat_template(
        full_messages,
        tokenize=False,
        add_generation_prompt=False,
        enable_thinking=False,
    )
    prompt_batch = processor(
        text=[prompt_text],
        images=[image],
        return_tensors="pt",
        max_pixels=MAX_PIXELS,
    )
    full_batch = processor(
        text=[full_text],
        images=[image],
        return_tensors="pt",
        max_pixels=MAX_PIXELS,
    )
    prompt_ids = prompt_batch["input_ids"][0].tolist()
    full_ids = full_batch["input_ids"][0].tolist()
    common = 0
    while (
        common < min(len(prompt_ids), len(full_ids))
        and prompt_ids[common] == full_ids[common]
    ):
        common += 1
    labels = full_batch["input_ids"].clone()
    labels[:, :common] = -100
    full_batch["labels"] = labels
    return full_batch


@app.function(
    image=image,
    gpu="L40S",
    cpu=8,
    memory=64 * 1024,
    volumes={
        "/data": data_volume,
        "/models": models_volume,
        "/runs": runs_volume,
    },
    timeout=15 * 60,
    max_containers=1,
)
def run_smoke() -> str:
    import torch
    from PIL import Image
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import (
        AutoModelForImageTextToText,
        AutoProcessor,
        BitsAndBytesConfig,
    )

    started = datetime.now(UTC)
    timer = time.perf_counter()
    data_volume.reload()
    models_volume.reload()
    runs_volume.reload()

    with open(MANIFEST_PATH, "r", encoding="utf-8", newline="") as handle:
        rows = [
            item
            for item in csv.DictReader(handle)
            if item["split"] == "train"
            and item["task"] in {"oct_uveitis_4class", "oct_aux_4class"}
        ]
    known_image = (
        "/data/data/data/01_uveitis_oct/01_uveitis_oct/"
        "Optical Coherence Tomography (OCT) Images of Proliferative "
        "Vitreoretinopathy, Uveitis, and Normal Eyes/"
        "Intermediate+Posterior Uveitis/Int+Post Uveitis 1.jpeg"
    )
    if not Path(known_image).is_file():
        raise FileNotFoundError(known_image)
    image_path = known_image
    row = rows[0]
    sample_image = Image.open(image_path).convert("RGB")

    processor = AutoProcessor.from_pretrained(MODEL_PATH, local_files_only=True)
    batch = _encode_example(
        processor,
        sample_image,
        task=str(row["task"]),
        label=str(row["label"]),
    )

    quantization = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    model = AutoModelForImageTextToText.from_pretrained(
        MODEL_PATH,
        local_files_only=True,
        quantization_config=quantization,
        torch_dtype=torch.bfloat16,
        device_map={"": 0},
        attn_implementation="sdpa",
        low_cpu_mem_usage=True,
    )
    model = prepare_model_for_kbit_training(
        model,
        use_gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
    )
    model.config.use_cache = False
    model = get_peft_model(
        model,
        LoraConfig(
            r=8,
            lora_alpha=16,
            lora_dropout=0.05,
            bias="none",
            task_type="CAUSAL_LM",
            target_modules=[
                "q_proj",
                "k_proj",
                "v_proj",
                "o_proj",
                "gate_proj",
                "up_proj",
                "down_proj",
            ],
        ),
    )
    model.train()
    optimizer = torch.optim.AdamW(
        (parameter for parameter in model.parameters() if parameter.requires_grad),
        lr=1e-4,
    )

    batch = {
        key: value.to("cuda") if torch.is_tensor(value) else value
        for key, value in batch.items()
    }
    if batch["input_ids"].shape[1] > MAX_LENGTH:
        raise ValueError(
            f"Smoke sample is {batch['input_ids'].shape[1]} tokens, "
            f"above MAX_LENGTH={MAX_LENGTH}"
        )

    torch.cuda.reset_peak_memory_stats()
    step_started = time.perf_counter()
    output = model(**batch)
    loss = output.loss
    loss.backward()
    optimizer.step()
    optimizer.zero_grad(set_to_none=True)
    torch.cuda.synchronize()
    step_seconds = time.perf_counter() - step_started

    run_dir = Path(RUN_ROOT)
    adapter_dir = run_dir / "final_adapter"
    adapter_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(adapter_dir)
    processor.save_pretrained(run_dir / "processor")
    config = {
        "run_id": RUN_ID,
        "base_model": QWEN4B_SUBDIR,
        "data_volume": DATA_VOLUME_NAME,
        "models_volume": MODELS_VOLUME_NAME,
        "runs_volume": RUNS_VOLUME_NAME,
        "started_at": started.isoformat(),
        "quantization": "4-bit NF4, bfloat16 compute, double quant",
        "lora": {
            "r": 8,
            "alpha": 16,
            "dropout": 0.05,
            "target_modules": [
                "q_proj",
                "k_proj",
                "v_proj",
                "o_proj",
                "gate_proj",
                "up_proj",
                "down_proj",
            ],
        },
        "max_pixels": MAX_PIXELS,
        "max_length": MAX_LENGTH,
        "sample_image": image_path,
        "sample_task": str(row["task"]),
        "sample_label": str(row["label"]),
    }
    (run_dir / "config.json").write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    metrics = {
        "status": "ok",
        "loss": float(loss.detach().cpu()),
        "step_seconds": step_seconds,
        "sequence_tokens": int(batch["input_ids"].shape[1]),
        "input_pixels": int(batch["pixel_values"].shape[0]),
        "peak_gpu_memory_gib": torch.cuda.max_memory_allocated() / 1024**3,
        "gpu_name": torch.cuda.get_device_name(0),
        "total_seconds": time.perf_counter() - timer,
        "finished_at": datetime.now(UTC).isoformat(),
    }
    (run_dir / "smoke_metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (run_dir / "model_card.md").write_text(
        "# Qwen3.5-4B smoke run\n\n"
        "Single-sample QLoRA forward/backward validation. "
        "Do not use this adapter as a trained clinical model.\n",
        encoding="utf-8",
    )
    runs_volume.commit()
    return json.dumps(metrics, indent=2, ensure_ascii=False)


@app.local_entrypoint()
def main() -> None:
    print(run_smoke.remote())

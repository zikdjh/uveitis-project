"""Run a small QLoRA smoke test for Qwen3.5-4B on the local RTX 4060.

This is a hardware and training-stack check, not a clinically useful training
run. It uses the real manifest and images, 4-bit NF4 quantization, short image
tokens, and gradient checkpointing. A successful result proves that one
forward/backward/optimizer step can execute on the local GPU.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import threading
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MODEL_DIR = ROOT / "model-training" / "models" / "qwen" / "Qwen3.5-4B"
MANIFEST_PATH = ROOT / "model-training" / "datasets" / "training" / "manifest.csv"
ARTIFACTS_ROOT = ROOT / "model-training" / "assets" / "qwen3.5-4b"

PHASE1_TASKS = {
    "oct_uveitis_4class",
    "fundus_toxo_binary",
    "fundus_toxo_activity_3class",
    "eye_five_class",
    "oct_aux_4class",
    "uwf_7class",
    "uwf_uveitis_binary",
}

TASK_LABELS = {
    "oct_uveitis_4class": [
        "Intermediate+Posterior Uveitis",
        "Normal",
        "Panuveitis",
        "RRD-PVR",
    ],
    "fundus_toxo_binary": ["healthy", "toxoplasmosis"],
    "fundus_toxo_activity_3class": ["active", "healthy", "inactive"],
    "eye_five_class": [
        "Cataract",
        "Conjunctivitis",
        "Eyelid",
        "Normal",
        "Uveitis",
    ],
    "oct_aux_4class": ["CNV", "DME", "DRUSEN", "NORMAL"],
    "uwf_7class": ["AMD", "DR", "Healthy", "PM", "RD", "RVO", "Uveitis"],
    "uwf_uveitis_binary": ["non_uveitis", "uveitis"],
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _load_train_rows(limit: int) -> list[dict]:
    with MANIFEST_PATH.open("r", encoding="utf-8", newline="") as handle:
        rows = [
            row
            for row in csv.DictReader(handle)
            if row["split"] == "train" and row["task"] in PHASE1_TASKS
        ]
    if not rows:
        raise ValueError("No stage-one training rows found in the manifest")

    # Keep the smoke sample deterministic while exercising multiple tasks when
    # more than one optimizer step is requested.
    selected: list[dict] = []
    seen_tasks: set[str] = set()
    for row in rows:
        if row["task"] not in seen_tasks:
            selected.append(row)
            seen_tasks.add(row["task"])
    for row in rows:
        if row not in selected:
            selected.append(row)
        if len(selected) >= limit:
            break
    return selected[:limit]


def _image_path(row: dict) -> Path:
    return ROOT / "model-training" / "datasets" / "training" / row["image"]


def _build_prompt(task: str, label: str) -> tuple[str, str]:
    allowed = TASK_LABELS[task]
    if label not in allowed:
        raise ValueError(f"Unexpected label {label!r} for {task!r}")
    prompt = (
        "Classify this retinal image. Do not infer any finding that is not "
        f"visible. Task: {task}. Allowed labels: {json.dumps(allowed)}. "
        "Choose exactly one allowed label and return only compact JSON with "
        '{"label":"...","requires_human_review":true}.'
    )
    answer = json.dumps(
        {"label": label, "requires_human_review": True},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return prompt, answer


def _encode_example(
    processor,
    image,
    prompt: str,
    answer: str,
    *,
    image_pixels: int,
    max_length: int,
) -> dict:
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
    full_text = processor.apply_chat_template(
        messages + [{"role": "assistant", "content": answer}],
        tokenize=False,
        add_generation_prompt=False,
        enable_thinking=False,
    )
    image_size = {
        "shortest_edge": image_pixels,
        "longest_edge": image_pixels,
    }
    prompt_batch = processor(
        text=[prompt_text],
        images=[image],
        return_tensors="pt",
        size=image_size,
    )
    full_batch = processor(
        text=[full_text],
        images=[image],
        return_tensors="pt",
        size=image_size,
    )
    if full_batch["input_ids"].shape[1] > max_length:
        raise ValueError(
            f"Encoded sample has {full_batch['input_ids'].shape[1]} tokens, "
            f"above --max-length={max_length}"
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


class MemoryMonitor:
    def __init__(self, output_path: Path, torch, interval_seconds: float = 2.0):
        self.output_path = output_path
        self.torch = torch
        self.interval_seconds = interval_seconds
        self.stop_event = threading.Event()
        self.thread = threading.Thread(
            target=self._run,
            name="cuda-memory-monitor",
            daemon=True,
        )

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=10)

    def _run(self) -> None:
        with self.output_path.open("w", encoding="utf-8") as handle:
            while not self.stop_event.wait(self.interval_seconds):
                allocated = self.torch.cuda.memory_allocated() / 1024**3
                reserved = self.torch.cuda.memory_reserved() / 1024**3
                free, total = self.torch.cuda.mem_get_info()
                sample = {
                    "time": datetime.now(UTC).isoformat(),
                    "allocated_gib": allocated,
                    "reserved_gib": reserved,
                    "device_free_gib": free / 1024**3,
                    "device_total_gib": total / 1024**3,
                }
                handle.write(json.dumps(sample) + "\n")
                handle.flush()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="local-4060-smoke-20261025-01")
    parser.add_argument("--steps", type=int, default=1)
    parser.add_argument("--image-pixels", type=int, default=16_384)
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--lora-r", type=int, default=8)
    parser.add_argument("--monitor-seconds", type=float, default=2.0)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.steps < 1:
        raise ValueError("--steps must be positive")
    if not MODEL_DIR.is_dir():
        raise FileNotFoundError(MODEL_DIR)
    if not MANIFEST_PATH.is_file():
        raise FileNotFoundError(MANIFEST_PATH)

    import torch
    from PIL import Image
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import (
        AutoModelForImageTextToText,
        AutoProcessor,
        BitsAndBytesConfig,
    )

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available")
    if not torch.cuda.is_bf16_supported():
        raise RuntimeError("The local GPU does not support bfloat16")

    run_dir = ARTIFACTS_ROOT / args.run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    monitor = MemoryMonitor(
        run_dir / "memory_monitor.jsonl",
        torch,
        interval_seconds=args.monitor_seconds,
    )
    started_at = datetime.now(UTC)
    timer = time.perf_counter()
    status = "running"
    metrics: dict = {
        "run_id": args.run_id,
        "status": status,
        "started_at": started_at.isoformat(),
        "model_dir": str(MODEL_DIR),
        "manifest": str(MANIFEST_PATH),
        "manifest_sha256": _sha256(MANIFEST_PATH),
        "gpu": {
            "name": torch.cuda.get_device_name(0),
            "total_memory_gib": torch.cuda.get_device_properties(0).total_memory
            / 1024**3,
            "compute_capability": list(torch.cuda.get_device_capability(0)),
        },
        "configuration": {
            "quantization": "4-bit NF4, bfloat16 compute, double quant",
            "lora_r": args.lora_r,
            "lora_alpha": args.lora_r * 2,
            "gradient_checkpointing": True,
            "image_pixels": args.image_pixels,
            "max_length": args.max_length,
            "requested_steps": args.steps,
            "learning_rate": args.learning_rate,
        },
    }

    model = None
    optimizer = None
    monitor.start()
    try:
        rows = _load_train_rows(args.steps)
        processor = AutoProcessor.from_pretrained(
            MODEL_DIR,
            local_files_only=True,
        )
        quantization = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )
        torch.cuda.reset_peak_memory_stats()
        model = AutoModelForImageTextToText.from_pretrained(
            MODEL_DIR,
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
        if hasattr(model.config, "text_config"):
            model.config.text_config.use_cache = False
        model = get_peft_model(
            model,
            LoraConfig(
                r=args.lora_r,
                lora_alpha=args.lora_r * 2,
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
        trainable_parameters = [
            parameter
            for parameter in model.parameters()
            if parameter.requires_grad
        ]
        if not trainable_parameters:
            raise RuntimeError("PEFT did not expose any trainable parameters")
        optimizer = torch.optim.AdamW(
            trainable_parameters,
            lr=args.learning_rate,
        )
        torch.cuda.synchronize()
        metrics["after_load"] = {
            "allocated_gib": torch.cuda.memory_allocated() / 1024**3,
            "reserved_gib": torch.cuda.memory_reserved() / 1024**3,
            "trainable_parameters": sum(
                parameter.numel() for parameter in trainable_parameters
            ),
        }
        print(
            json.dumps(
                {"event": "model_loaded", **metrics["after_load"]},
                ensure_ascii=False,
            ),
            flush=True,
        )

        step_metrics: list[dict] = []
        for step_index, row in enumerate(rows, start=1):
            image_path = _image_path(row)
            if not image_path.is_file():
                raise FileNotFoundError(image_path)
            prompt, answer = _build_prompt(row["task"], row["label"])
            with Image.open(image_path) as source:
                image = source.convert("RGB")
            batch = _encode_example(
                processor,
                image,
                prompt,
                answer,
                image_pixels=args.image_pixels,
                max_length=args.max_length,
            )
            batch = {
                key: value.to("cuda") if torch.is_tensor(value) else value
                for key, value in batch.items()
            }
            optimizer.zero_grad(set_to_none=True)
            step_started = time.perf_counter()
            output = model(**batch)
            loss = output.loss
            if not loss.requires_grad:
                raise RuntimeError("The training loss does not require gradients")
            loss.backward()
            gradient_norm = torch.nn.utils.clip_grad_norm_(
                trainable_parameters,
                1.0,
            )
            optimizer.step()
            torch.cuda.synchronize()
            step_seconds = time.perf_counter() - step_started
            step_metrics.append(
                {
                    "step": step_index,
                    "task": row["task"],
                    "label": row["label"],
                    "image": str(image_path.relative_to(ROOT)),
                    "loss": float(loss.detach().cpu()),
                    "gradient_norm": float(gradient_norm.detach().cpu()),
                    "sequence_tokens": int(batch["input_ids"].shape[1]),
                    "visual_tokens": int(
                        batch["image_grid_thw"].prod(dim=-1).sum().item()
                    ),
                    "step_seconds": step_seconds,
                    "peak_allocated_gib": torch.cuda.max_memory_allocated()
                    / 1024**3,
                    "peak_reserved_gib": torch.cuda.max_memory_reserved()
                    / 1024**3,
                }
            )
            print(
                json.dumps(
                    {"event": "optimizer_step", **step_metrics[-1]},
                    ensure_ascii=False,
                ),
                flush=True,
            )
            del output, loss, batch

        adapter_dir = run_dir / "final_adapter"
        model.save_pretrained(adapter_dir)
        processor.save_pretrained(run_dir / "processor")
        adapter_weights = adapter_dir / "adapter_model.safetensors"
        adapter_config = adapter_dir / "adapter_config.json"
        if not adapter_weights.is_file() or not adapter_config.is_file():
            raise RuntimeError("PEFT did not save a complete adapter")

        status = "ok"
        metrics.update(
            {
                "status": status,
                "steps": step_metrics,
                "adapter": {
                    "directory": str(adapter_dir.relative_to(ROOT)),
                    "adapter_model_sha256": _sha256(adapter_weights),
                    "adapter_config_sha256": _sha256(adapter_config),
                    "bytes": adapter_weights.stat().st_size,
                },
                "peak_allocated_gib": torch.cuda.max_memory_allocated()
                / 1024**3,
                "peak_reserved_gib": torch.cuda.max_memory_reserved() / 1024**3,
            }
        )
    except Exception as exc:
        status = "failed"
        metrics.update(
            {
                "status": status,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
        )
        raise
    finally:
        monitor.stop()
        if torch.cuda.is_initialized():
            metrics["final"] = {
                "allocated_gib": torch.cuda.memory_allocated() / 1024**3,
                "reserved_gib": torch.cuda.memory_reserved() / 1024**3,
                "peak_allocated_gib": torch.cuda.max_memory_allocated()
                / 1024**3,
                "peak_reserved_gib": torch.cuda.max_memory_reserved() / 1024**3,
            }
        metrics["total_seconds"] = time.perf_counter() - timer
        metrics["finished_at"] = datetime.now(UTC).isoformat()
        _write_json(run_dir / "smoke_metrics.json", metrics)
        _write_json(
            run_dir / "run_manifest.json",
            {
                "run_id": args.run_id,
                "status": status,
                "python": str(Path(__import__("sys").executable)),
                "torch": torch.__version__,
                "cuda": torch.version.cuda,
                "gpu": torch.cuda.get_device_name(0),
                "metrics": "smoke_metrics.json",
                "memory_monitor": "memory_monitor.jsonl",
            },
        )
        print(json.dumps(metrics, indent=2, ensure_ascii=False), flush=True)
        del model, optimizer
        if torch.cuda.is_initialized():
            torch.cuda.empty_cache()


if __name__ == "__main__":
    main()

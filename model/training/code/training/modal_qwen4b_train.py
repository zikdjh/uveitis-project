"""Train a Qwen3.5-4B QLoRA adapter for the stage-one uveitis tasks.

Run from the repository root:

    $env:HTTP_PROXY = ""
    $env:HTTPS_PROXY = ""
    $env:ALL_PROXY = ""
    .\model\training\.venv-modal\Scripts\modal.exe run model\training\code\training\modal_qwen4b_train.py

The run uses a deterministic task-stratified subset, a frozen test split from
the manifest, an L40S GPU, and a wall-clock budget that stops between
optimizer steps. Checkpoints and the final adapter are persisted in the
``uveitis-runs`` volume.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import random
import shutil
import subprocess
import time
import traceback
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

import modal

from modal_volumes import (
    DATA_ROOT,
    MANIFEST_PATH,
    PHASE1_TASKS,
    QWEN4B_SUBDIR,
    RUNS_VOLUME_NAME,
    TASK_LABELS,
    data_volume,
    models_volume,
    runs_volume,
)


APP_NAME = "uveitis-qwen4b-train"
MODEL_PATH = f"/models/{QWEN4B_SUBDIR}"
RUN_ID = os.environ.get("UV_RUN_ID", "qwen4b-stage1-20261025-01")
RUN_ROOT = f"/runs/qwen3.5-4b/{RUN_ID}"

TRAIN_LIMIT = int(os.environ.get("UV_TRAIN_LIMIT", "900"))
MAX_STEPS = int(os.environ.get("UV_MAX_STEPS", "30"))
MAX_MINUTES = int(os.environ.get("UV_MAX_MINUTES", "20"))
MAX_PIXELS = int(os.environ.get("UV_MAX_PIXELS", str(448 * 448)))
MAX_LENGTH = int(os.environ.get("UV_MAX_LENGTH", "1024"))
GRAD_ACCUM = int(os.environ.get("UV_GRAD_ACCUM", "8"))
SAVE_EVERY_STEPS = int(os.environ.get("UV_SAVE_EVERY_STEPS", "10"))
VALIDATION_EVERY_STEPS = int(os.environ.get("UV_VALIDATION_EVERY_STEPS", "10"))
VALIDATION_LIMIT = int(os.environ.get("UV_VALIDATION_LIMIT", "96"))
EARLY_STOPPING_PATIENCE = int(os.environ.get("UV_EARLY_STOPPING_PATIENCE", "3"))
MAX_CONSECUTIVE_ERRORS = int(os.environ.get("UV_MAX_CONSECUTIVE_ERRORS", "3"))
RUN_KIND = os.environ.get("UV_RUN_KIND", "calibration")
RESUME = os.environ.get("UV_RESUME", "0").lower() in {"1", "true", "yes"}
INIT_RUN_ID = os.environ.get("UV_INIT_RUN_ID", "")
INIT_STEP = int(os.environ.get("UV_INIT_STEP", "0"))
FOCUS01 = os.environ.get("UV_FOCUS01", "0").lower() in {"1", "true", "yes"}
LEARNING_RATE = float(os.environ.get("UV_LEARNING_RATE", "1e-4"))
PAIRED_SELECTION_SHA256 = os.environ.get("UV_PAIRED_SELECTION_SHA256", "")
CYCLIC = os.environ.get("UV_CYCLIC", "0").lower() in {"1", "true", "yes"}
EVAL_STEP = int(os.environ.get("UV_EVAL_STEP", "0"))
SEED = 20261025

TRANSFORMERS_COMMIT = "50e35cc0ca18ec19b80653690de553e6decf74f5"
PEFT_COMMIT = "7d6315ae910bf62b6044a7ca917bccf5881f5e43"

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


def _apply_run_options(options: dict | None) -> None:
    """Apply launch values in the remote process instead of relying on inherited env."""
    global RUN_ID
    global RUN_ROOT
    global TRAIN_LIMIT
    global MAX_STEPS
    global MAX_MINUTES
    global MAX_PIXELS
    global MAX_LENGTH
    global GRAD_ACCUM
    global SAVE_EVERY_STEPS
    global VALIDATION_EVERY_STEPS
    global VALIDATION_LIMIT
    global EARLY_STOPPING_PATIENCE
    global MAX_CONSECUTIVE_ERRORS
    global RUN_KIND
    global RESUME
    global INIT_RUN_ID
    global INIT_STEP
    global FOCUS01
    global LEARNING_RATE
    global PAIRED_SELECTION_SHA256
    global CYCLIC
    global EVAL_STEP

    options = options or {}
    RUN_ID = str(options.get("run_id", RUN_ID))
    RUN_ROOT = f"/runs/qwen3.5-4b/{RUN_ID}"
    TRAIN_LIMIT = int(options.get("train_limit", TRAIN_LIMIT))
    MAX_STEPS = int(options.get("max_steps", MAX_STEPS))
    MAX_MINUTES = int(options.get("max_minutes", MAX_MINUTES))
    MAX_PIXELS = int(options.get("max_pixels", MAX_PIXELS))
    MAX_LENGTH = int(options.get("max_length", MAX_LENGTH))
    GRAD_ACCUM = max(1, int(options.get("grad_accum", GRAD_ACCUM)))
    SAVE_EVERY_STEPS = int(options.get("save_every_steps", SAVE_EVERY_STEPS))
    VALIDATION_EVERY_STEPS = int(
        options.get("validation_every_steps", VALIDATION_EVERY_STEPS)
    )
    VALIDATION_LIMIT = int(options.get("validation_limit", VALIDATION_LIMIT))
    EARLY_STOPPING_PATIENCE = int(
        options.get("early_stopping_patience", EARLY_STOPPING_PATIENCE)
    )
    MAX_CONSECUTIVE_ERRORS = max(
        1, int(options.get("max_consecutive_errors", MAX_CONSECUTIVE_ERRORS))
    )
    RUN_KIND = str(options.get("run_kind", RUN_KIND))
    RESUME = str(options.get("resume", "0")).lower() in {"1", "true", "yes"}
    INIT_RUN_ID = str(options.get("init_run_id", INIT_RUN_ID))
    INIT_STEP = int(options.get("init_step", INIT_STEP))
    FOCUS01 = str(options.get("focus01", "0")).lower() in {"1", "true", "yes"}
    LEARNING_RATE = float(options.get("learning_rate", LEARNING_RATE))
    PAIRED_SELECTION_SHA256 = str(
        options.get("paired_selection_sha256", PAIRED_SELECTION_SHA256)
    )
    CYCLIC = str(options.get("cyclic", "0")).lower() in {"1", "true", "yes"}
    EVAL_STEP = int(options.get("eval_step", EVAL_STEP))


def _load_rows() -> tuple[list[dict], list[dict]]:
    with open(MANIFEST_PATH, "r", encoding="utf-8", newline="") as handle:
        rows = [
            row for row in csv.DictReader(handle) if row["task"] in PHASE1_TASKS
        ]
    train = [row for row in rows if row["split"] == "train"]
    test = [row for row in rows if row["split"] == "test"]
    if not train or not test:
        raise ValueError("The manifest must contain stage-one train and test rows")
    return train, test


def _balanced_subset(rows: list[dict], limit: int) -> list[dict]:
    buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        buckets[(row["task"], row["label"])].append(row)
    rng = random.Random(SEED)
    for values in buckets.values():
        rng.shuffle(values)
    selected: list[dict] = []
    keys = sorted(buckets)
    while len(selected) < min(limit, len(rows)):
        made_progress = False
        for key in keys:
            values = buckets[key]
            if values:
                selected.append(values.pop())
                made_progress = True
                if len(selected) >= limit:
                    break
        if not made_progress:
            break
    rng.shuffle(selected)
    return selected


def _focus01_subset(rows: list[dict], limit: int = 400) -> list[dict]:
    """Oversample the two weak OCT classes without touching the test split."""
    quotas = {
        ("oct_uveitis_4class", "Panuveitis"): 50,
        ("oct_uveitis_4class", "Intermediate+Posterior Uveitis"): 44,
        ("oct_uveitis_4class", "Normal"): 24,
        ("oct_uveitis_4class", "RRD-PVR"): 22,
        ("fundus_toxo_binary", "healthy"): 40,
        ("fundus_toxo_binary", "toxoplasmosis"): 40,
        ("eye_five_class", "Cataract"): 20,
        ("eye_five_class", "Conjunctivitis"): 20,
        ("eye_five_class", "Eyelid"): 20,
        ("eye_five_class", "Normal"): 20,
        ("eye_five_class", "Uveitis"): 20,
        ("oct_aux_4class", "CNV"): 20,
        ("oct_aux_4class", "DME"): 20,
        ("oct_aux_4class", "DRUSEN"): 20,
        ("oct_aux_4class", "NORMAL"): 20,
    }
    if sum(quotas.values()) != limit:
        raise ValueError("focus01 quotas must add up to the exposure limit")

    buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        buckets[(row["task"], row["label"])].append(row)
    missing = [key for key in quotas if not buckets[key]]
    if missing:
        raise ValueError(f"Missing focus01 train buckets: {missing}")

    rng = random.Random(SEED + 2)
    selected: list[dict] = []
    for key in sorted(quotas):
        values = buckets[key]
        selected.extend(rng.choice(values) for _ in range(quotas[key]))
    rng.shuffle(selected)
    return selected


def _split_validation(
    rows: list[dict], fraction: float = 0.15
) -> tuple[list[dict], list[dict]]:
    """Split train-only rows deterministically, keeping every task/class present."""
    buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        buckets[(row["task"], row["label"])].append(row)
    rng = random.Random(SEED + 1)
    validation: list[dict] = []
    fitted: list[dict] = []
    for key in sorted(buckets):
        values = buckets[key]
        values.sort(key=lambda row: row["source_group"] + "\0" + row["image"])
        rng.shuffle(values)
        validation_count = min(max(1, round(len(values) * fraction)), len(values) - 1)
        validation.extend(values[:validation_count])
        fitted.extend(values[validation_count:])
    rng.shuffle(fitted)
    rng.shuffle(validation)
    return fitted, validation


def _image_path(row: dict) -> str:
    return f"{DATA_ROOT}/{row['dataset']}/{row['source_image']}"


def _build_training_example(processor, image, task: str, label: str) -> tuple[str, dict]:
    labels = TASK_LABELS[task]
    if label not in labels:
        raise ValueError(f"Unexpected label {label!r} for task {task!r}")
    prompt = (
        "Classify this retinal image. Do not infer any finding that is not "
        f"visible. Task: {task}. Allowed labels: {json.dumps(labels)}. "
        "Choose exactly one allowed label and return only compact JSON with "
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
    return prompt, {"label": label, "requires_human_review": True}


def _encode_training_example(
    processor, image, prompt: str, answer: dict
) -> dict:
    answer_text = json.dumps(
        answer, ensure_ascii=False, separators=(",", ":")
    )
    full_text = processor.apply_chat_template(
        [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": prompt},
                ],
            },
            {"role": "assistant", "content": answer_text},
        ],
        tokenize=False,
        add_generation_prompt=False,
        enable_thinking=False,
    )
    prompt_text = processor.apply_chat_template(
        [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": prompt},
                ],
            }
        ],
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )
    full_batch = processor(
        text=[full_text],
        images=[image],
        return_tensors="pt",
        max_pixels=MAX_PIXELS,
    )
    prompt_ids = processor(
        text=[prompt_text],
        images=[image],
        return_tensors="pt",
        max_pixels=MAX_PIXELS,
    )["input_ids"][0].tolist()
    full_ids = full_batch["input_ids"][0].tolist()
    common = 0
    while (
        common < min(len(prompt_ids), len(full_ids))
        and prompt_ids[common] == full_ids[common]
    ):
        common += 1
    labels_tensor = full_batch["input_ids"].clone()
    labels_tensor[:, :common] = -100
    full_batch["labels"] = labels_tensor
    return full_batch


def _encode_example(processor, image, task: str, label: str) -> dict:
    prompt_text, answer = _build_training_example(processor, image, task, label)
    return _encode_training_example(processor, image, prompt_text, answer)


def _evaluate_validation(
    model,
    processor,
    rows: list[dict],
    *,
    torch,
    Image,
    max_rows: int,
) -> dict:
    """Compute held-out loss without updating weights or the frozen test split."""
    model.eval()
    losses: list[float] = []
    skipped = 0
    with torch.inference_mode():
        for row in rows[:max_rows]:
            source = None
            try:
                source = Image.open(_image_path(row)).convert("RGB")
                batch = _encode_example(
                    processor, source, task=row["task"], label=row["label"]
                )
                source.close()
                source = None
                if batch["input_ids"].shape[1] > MAX_LENGTH:
                    skipped += 1
                    continue
                batch = {
                    key: value.to("cuda") if torch.is_tensor(value) else value
                    for key, value in batch.items()
                }
                output = model(**batch)
                losses.append(float(output.loss.detach().cpu()))
                del output, batch
            except torch.cuda.OutOfMemoryError:
                skipped += 1
                torch.cuda.empty_cache()
            except Exception as exc:
                skipped += 1
                print(
                    f"Validation skipped {row['image']}: "
                    f"{type(exc).__name__}: {exc}",
                    flush=True,
                )
            finally:
                if source is not None:
                    source.close()
    model.train()
    return {
        "loss": sum(losses) / len(losses) if losses else None,
        "evaluated": len(losses),
        "skipped": skipped,
        "note": "Generation and task-level macro-F1 belong in the evaluator.",
    }


def _metric_value(labels: list[str], predictions: list[str]) -> dict:
    """Return accuracy and macro-F1 without requiring scikit-learn."""
    if not labels:
        return {"samples": 0, "accuracy": None, "macro_f1": None}
    classes = sorted(set(labels) | set(predictions))
    f1_scores: list[float] = []
    per_class: dict[str, dict] = {}
    for label in classes:
        true_positive = sum(
            actual == label and predicted == label
            for actual, predicted in zip(labels, predictions)
        )
        false_positive = sum(
            actual != label and predicted == label
            for actual, predicted in zip(labels, predictions)
        )
        false_negative = sum(
            actual == label and predicted != label
            for actual, predicted in zip(labels, predictions)
        )
        denominator = 2 * true_positive + false_positive + false_negative
        f1 = 2 * true_positive / denominator if denominator else 0.0
        f1_scores.append(f1)
        per_class[label] = {
            "precision": (
                true_positive / (true_positive + false_positive)
                if true_positive + false_positive
                else 0.0
            ),
            "recall": (
                true_positive / (true_positive + false_negative)
                if true_positive + false_negative
                else 0.0
            ),
            "f1": f1,
            "support": sum(actual == label for actual in labels),
        }
    return {
        "samples": len(labels),
        "accuracy": sum(a == p for a, p in zip(labels, predictions)) / len(labels),
        "macro_f1": sum(f1_scores) / len(f1_scores),
        "per_class": per_class,
    }


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _paired_eval(run_id: str, step: int) -> dict:
    """Run the evaluator on the same frozen 40-row set used for step 100."""
    if not PAIRED_SELECTION_SHA256:
        raise ValueError("paired_selection_sha256 is required for metric selection")
    output_dir = f"paired40-step-{step:06d}"
    command = [
        "python",
        "-m",
        "modal_qwen4b_eval",
    ]
    environment = {
        **os.environ,
        "UV_RUN_ID": run_id,
        "UV_CHECKPOINT_STEP": str(step),
        "UV_EVAL_LIMIT": "40",
        "UV_EVAL_OUTPUT_DIR": output_dir,
        "UV_REQUIRED_SELECTION_SHA256": PAIRED_SELECTION_SHA256,
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
    }
    completed = subprocess.run(
        command,
        cwd=str(Path(__file__).resolve().parent),
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    output_lines = completed.stdout.strip().splitlines()
    if not output_lines:
            raise RuntimeError("Paired evaluation subprocess produced no JSON output")
    metrics = json.loads(output_lines[-1])
    runs_volume.reload()
    return metrics


def _metric_key(metrics: dict) -> tuple[float, float]:
    """Prefer OCT uveitis F1, then overall task F1 without hiding regressions."""
    tasks = metrics.get("tasks", {})
    oct_f1 = tasks.get("oct_uveitis_4class", {}).get("macro_f1")
    all_f1 = [
        float(task["macro_f1"])
        for task in tasks.values()
        if task.get("macro_f1") is not None
    ]
    return float(oct_f1 or 0.0), sum(all_f1) / len(all_f1) if all_f1 else 0.0


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
    timeout=5 * 60 * 60,
    max_containers=1,
)
def train(options: dict | None = None) -> str:
    _apply_run_options(options)
    global EVAL_STEP
    import gc
    import torch
    from PIL import Image
    from peft import (
        LoraConfig,
        get_peft_model,
        prepare_model_for_kbit_training,
        set_peft_model_state_dict,
    )
    from safetensors.torch import load_file
    from transformers import (
        AutoModelForImageTextToText,
        AutoProcessor,
        BitsAndBytesConfig,
    )

    started = datetime.now(UTC)
    timer = time.perf_counter()
    deadline = timer + MAX_MINUTES * 60
    data_volume.reload()
    models_volume.reload()
    runs_volume.reload()

    all_train, holdout = _load_rows()
    fitted_rows, validation_rows = _split_validation(all_train)
    if PAIRED_SELECTION_SHA256:
        print(
            "Paired evaluation is disabled during training; for this cyclic run "
            "checkpoint persistence is driven by the external budget monitor.",
            flush=True,
        )
    train_rows = (
        _focus01_subset(fitted_rows, TRAIN_LIMIT)
        if FOCUS01
        else _balanced_subset(fitted_rows, TRAIN_LIMIT)
    )
    if VALIDATION_LIMIT > 0 and len(validation_rows) > VALIDATION_LIMIT:
        validation_rows = _balanced_subset(validation_rows, VALIDATION_LIMIT)
    run_dir = Path(RUN_ROOT)
    if not RESUME and run_dir.exists() and any(run_dir.iterdir()):
        raise FileExistsError(
            f"{run_dir} already contains files; use a new run_id or explicit resume"
        )
    run_dir.mkdir(parents=True, exist_ok=True)
    baseline_metrics: dict = {}
    if PAIRED_SELECTION_SHA256:
        # The baseline metric is loaded from the promoted step 100 checkpoint.
        # It is a fixed external gate; the 40 test rows stay out of training.
        baseline_run_id = INIT_RUN_ID or RUN_ID
        baseline_step = INIT_STEP or 100
        baseline_metrics_file = (
            Path(f"/runs/qwen3.5-4b/{baseline_run_id}")
            / "paired40"
            / "eval_metrics.json"
        )
        if baseline_metrics_file.is_file():
            baseline_metrics = json.loads(
                baseline_metrics_file.read_text(encoding="utf-8")
            )
    _write_json(
        run_dir / "dataset_summary.json",
        {
            "manifest": MANIFEST_PATH,
            "stage": 1,
            "tasks": PHASE1_TASKS,
            "full_task_counts": dict(Counter(row["task"] for row in all_train)),
            "train_rows": len(train_rows),
            "unique_train_images": len(
                {(row["task"], row["image"]) for row in train_rows}
            ),
            "validation_rows": len(validation_rows),
            "holdout_rows": len(holdout),
            "train_label_counts": dict(
                Counter(f"{row['task']}::{row['label']}" for row in train_rows)
            ),
            "validation_label_counts": dict(
                Counter(f"{row['task']}::{row['label']}" for row in validation_rows)
            ),
            "holdout_label_counts": dict(
                Counter(f"{row['task']}::{row['label']}" for row in holdout)
            ),
            "manifest_sha256": _sha256(MANIFEST_PATH),
            "sampling": "focus01_weighted" if FOCUS01 else "balanced_first_exposure",
            "test_rows_in_training": sum(row["split"] == "test" for row in train_rows),
            "notes": [
                "Validation was split from train rows deterministically by task/label.",
                "The frozen test split never participates in training or checkpoint selection.",
                "03 is used as a prototype and is not a clinical test set.",
                "Training text contains only the true task and label.",
            ],
        },
    )

    processor = AutoProcessor.from_pretrained(MODEL_PATH, local_files_only=True)
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
    initial_adapter: dict | None = None
    imported_validation_loss = float("inf")
    source_metadata: dict = {}
    if INIT_RUN_ID:
        source_run_dir = Path(f"/runs/qwen3.5-4b/{INIT_RUN_ID}")
        source_checkpoint_dir = (
            source_run_dir / "checkpoints" / f"step-{INIT_STEP:06d}"
            if INIT_STEP > 0
            else source_run_dir / "best_adapter"
        )
        source_weights = source_checkpoint_dir / "adapter_model.safetensors"
        source_config = source_checkpoint_dir / "adapter_config.json"
        if not source_weights.is_file() or not source_config.is_file():
            raise FileNotFoundError(
                f"Initial adapter is incomplete: {source_checkpoint_dir}"
            )
        set_peft_model_state_dict(
            model,
            load_file(source_weights),
            adapter_name="default",
        )
        source_metadata_path = (
            source_run_dir / "best_checkpoint.json"
            if INIT_STEP == 0
            else source_checkpoint_dir / "checkpoint.json"
        )
        source_metadata = (
            json.loads(source_metadata_path.read_text(encoding="utf-8"))
            if source_metadata_path.is_file()
            else {}
        )
        imported_validation_loss = float(
            source_metadata.get("validation_loss", float("inf"))
        )
        initial_adapter_dir = run_dir / "initial_adapter"
        initial_adapter_dir.mkdir(parents=True, exist_ok=True)
        for name in ("adapter_config.json", "adapter_model.safetensors"):
            shutil.copy2(source_checkpoint_dir / name, initial_adapter_dir / name)
        initial_adapter = {
            "source_run_id": INIT_RUN_ID,
            "source_step": int(
                source_metadata.get("step", INIT_STEP or source_metadata.get("optimizer_step", 0))
            ),
            "source_checkpoint": str(source_checkpoint_dir),
            "source_validation_loss": imported_validation_loss,
            "adapter_sha256": {
                name: _sha256(initial_adapter_dir / name)
                for name in ("adapter_config.json", "adapter_model.safetensors")
            },
        }
        _write_json(initial_adapter_dir / "adapter_manifest.json", initial_adapter)
        print(
            f"Initialized adapter from {source_checkpoint_dir}, "
            f"validation_loss={imported_validation_loss}",
            flush=True,
        )
    model.train()
    optimizer = torch.optim.AdamW(
        (p for p in model.parameters() if p.requires_grad),
        lr=LEARNING_RATE,
    )
    config = {
        "run_id": RUN_ID,
        "learning_rate": LEARNING_RATE,
        "launch_options": options or {},
        "focus01": FOCUS01,
        "cyclic": CYCLIC,
        "initial_adapter": initial_adapter,
        "base_model": QWEN4B_SUBDIR,
        "base_quantization": "4-bit NF4, bfloat16 compute, double quant",
        "lora": {"r": 8, "alpha": 16, "dropout": 0.05},
        "train_rows": len(train_rows),
        "validation_rows": len(validation_rows),
        "holdout_rows": len(holdout),
        "run_kind": RUN_KIND,
        "max_steps": MAX_STEPS,
        "max_minutes": MAX_MINUTES,
        "grad_accum": GRAD_ACCUM,
        "save_every_steps": SAVE_EVERY_STEPS,
        "validation_every_steps": VALIDATION_EVERY_STEPS,
        "validation_limit": VALIDATION_LIMIT,
        "early_stopping_patience": EARLY_STOPPING_PATIENCE,
        "max_consecutive_errors": MAX_CONSECUTIVE_ERRORS,
        "max_pixels": MAX_PIXELS,
        "max_length": MAX_LENGTH,
        "seed": SEED,
        "training_framework": "transformers and peft pinned commits, manual loop",
        "transformers_commit": TRANSFORMERS_COMMIT,
        "peft_commit": PEFT_COMMIT,
        "output_volume": RUNS_VOLUME_NAME,
        "run_root": RUN_ROOT,
    }
    _write_json(run_dir / "config.json", config)

    metrics_file = run_dir / "train_metrics.jsonl"
    if not (RESUME and metrics_file.exists()):
        metrics_file.write_text("", encoding="utf-8")
    gradients: list[float] = []
    optimizer.zero_grad(set_to_none=True)
    torch.cuda.reset_peak_memory_stats()
    skipped = 0
    processed = 0
    attempted = 0
    completed = 0
    consecutive_errors = 0
    last_error: dict | None = None
    truncated_reason = "train_rows_exhausted"
    best_validation_loss = imported_validation_loss
    best_step = (
        int(initial_adapter["source_step"])
        if initial_adapter is not None
        else 0
    )
    best_checkpoint_path = (
        Path(initial_adapter["source_checkpoint"])
        if initial_adapter is not None
        else run_dir / "checkpoints"
    )
    best_source = "imported" if initial_adapter is not None else "training"
    best_metrics = baseline_metrics
    if EVAL_STEP > 0:
        evaluation_checkpoint = (
            run_dir / "checkpoints" / f"step-{EVAL_STEP:06d}"
        )
        evaluation_metrics_path = (
            run_dir / f"paired40-step-{EVAL_STEP:06d}" / "eval_metrics.json"
        )
        if not (evaluation_checkpoint / "adapter_model.safetensors").is_file():
            raise FileNotFoundError(evaluation_checkpoint)
        if not evaluation_metrics_path.is_file():
            raise FileNotFoundError(evaluation_metrics_path)
        best_metrics = json.loads(
            evaluation_metrics_path.read_text(encoding="utf-8")
        )
        best_validation_loss = float("-inf")
        best_step = EVAL_STEP
        best_checkpoint_path = evaluation_checkpoint
        best_source = "external_fixed_eval"
    stale_validations = 0
    start_step = time.perf_counter()
    last_step_time = 2.0

    def save_checkpoint(
        step: int,
        validation_loss: float | None,
        *,
        current_best: int | None = None,
        current_best_loss: float | None = None,
    ) -> None:
        checkpoint_name = f"step-{step:06d}"
        checkpoint_dir = run_dir / "checkpoints" / checkpoint_name
        model.save_pretrained(checkpoint_dir)
        processor.save_pretrained(checkpoint_dir / "processor")
        torch.save(
            {
                "optimizer": optimizer.state_dict(),
                "optimizer_step": step,
                "validation_loss": validation_loss,
                "seed": SEED,
                "processed_samples": processed,
                "skipped_samples": skipped,
                "attempted_samples": attempted,
                "best_step": (
                    current_best if current_best is not None else best_step
                ),
                "best_validation_loss": (
                    current_best_loss
                    if current_best_loss is not None
                    else best_validation_loss
                ),
            },
            checkpoint_dir / "training_state.pt",
        )
        _write_json(
            checkpoint_dir / "checkpoint.json",
            {
                "step": step,
                "validation_loss": validation_loss,
                "kind": "adapter_with_optimizer_state",
            },
        )
        _write_json(
            run_dir / "last_checkpoint.json",
            {
                "checkpoint_dir": str(checkpoint_dir),
                "optimizer_step": step,
                "processed_samples": processed,
                "skipped_samples": skipped,
                "attempted_samples": attempted,
            },
        )
        runs_volume.commit()

    resumed_from_step = 0
    resume_offset = 0
    target_steps = MAX_STEPS
    last_checkpoint_file = run_dir / "last_checkpoint.json"
    if RESUME and last_checkpoint_file.is_file():
        resume_info = json.loads(last_checkpoint_file.read_text(encoding="utf-8"))
        checkpoint_dir = Path(
            resume_info.get("checkpoint_dir")
            or resume_info.get("latest_checkpoint")
            or ""
        )
        training_state_path = checkpoint_dir / "training_state.pt"
        adapter_weights_path = checkpoint_dir / "adapter_model.safetensors"
        if not training_state_path.is_file() or not adapter_weights_path.is_file():
            raise FileNotFoundError(
                f"Incomplete checkpoint at {checkpoint_dir}; "
                "expected training_state.pt and adapter_model.safetensors"
            )
        from peft import set_peft_model_state_dict
        from safetensors.torch import load_file

        training_state = torch.load(
            training_state_path,
            map_location="cpu",
            weights_only=False,
        )
        set_peft_model_state_dict(
            model,
            load_file(adapter_weights_path),
            adapter_name="default",
        )
        optimizer.load_state_dict(training_state["optimizer"])
        resumed_from_step = int(training_state["optimizer_step"])
        completed = resumed_from_step
        processed = int(training_state.get("processed_samples", 0))
        skipped = int(training_state.get("skipped_samples", 0))
        attempted = int(
            training_state.get(
                "attempted_samples",
                processed + skipped,
            )
        )
        if "attempted_samples" not in training_state:
            rebuild_processed = 0
            rebuild_skipped = 0
            for previous_row in train_rows:
                rebuild_processed += 1
                previous_batch = None
                previous_source = None
                try:
                    previous_source = Image.open(
                        _image_path(previous_row)
                    ).convert("RGB")
                    previous_batch = _encode_example(
                        processor,
                        previous_source,
                        task=previous_row["task"],
                        label=previous_row["label"],
                    )
                except Exception:
                    rebuild_skipped += 1
                finally:
                    if previous_source is not None:
                        previous_source.close()
                if previous_batch is not None:
                    del previous_batch
                if rebuild_processed == processed:
                    break
            attempted = processed + rebuild_skipped
            print(
                f"Rebuilt resume cursor for legacy checkpoint: "
                f"processed={processed}, reconstructed_skipped={rebuild_skipped}",
                flush=True,
            )
        resume_offset = attempted
        best_step = int(training_state.get("best_step", completed))
        best_checkpoint_path = checkpoint_dir
        best_source = "resumed"
        if "best_validation_loss" in training_state:
            best_validation_loss = float(training_state["best_validation_loss"])
        else:
            best_metric_file = (
                run_dir / "checkpoints" / f"step-{best_step:06d}" / "checkpoint.json"
            )
            best_metric = (
                json.loads(best_metric_file.read_text(encoding="utf-8"))
                if best_metric_file.is_file()
                else {}
            )
            best_validation_loss = float(
                best_metric.get(
                    "validation_loss",
                    training_state.get("validation_loss", float("inf")),
                )
            )
        target_steps = completed + MAX_STEPS
        print(
            f"Resumed {checkpoint_dir}: step={completed}, "
            f"processed={processed}, skipped={skipped}, "
            f"attempted={attempted}, target_step={target_steps}",
            flush=True,
        )
    elif RESUME:
        print("No last_checkpoint.json found; starting from scratch", flush=True)

    training_index = resume_offset
    if CYCLIC:
        # Resume at the beginning of the next epoch. Replaying the uncommitted
        # tail after the last checkpoint makes the run reproducible.
        training_index = ((resume_offset // len(train_rows)) + 1) * len(train_rows)
    while training_index < target_steps * GRAD_ACCUM:
        if not CYCLIC and training_index >= len(train_rows):
            truncated_reason = "train_rows_exhausted"
            break
        row = train_rows[training_index % len(train_rows)] if CYCLIC else train_rows[training_index]
        training_index += 1
        attempted += 1
        batch = None
        image_batch = None
        loss_requires_grad = None
        logits_requires_grad = None
        remaining = deadline - time.perf_counter()
        if remaining < max(3 * last_step_time, 10):
            truncated_reason = "wall_clock_budget"
            break
        image_path = _image_path(row)
        source = None
        try:
            source = Image.open(image_path).convert("RGB")
            batch = _encode_example(
                processor, source, task=row["task"], label=row["label"]
            )
            image_batch = batch
            source.close()
            source = None
            if batch["input_ids"].shape[1] > MAX_LENGTH:
                skipped += 1
                continue
            batch = {
                key: value.to("cuda") if torch.is_tensor(value) else value
                for key, value in batch.items()
            }
            output = model(**batch)
            loss = output.loss
            loss_value = float(loss.detach().cpu())
            loss_requires_grad = bool(loss.requires_grad)
            logits_requires_grad = (
                bool(output.logits.requires_grad)
                if getattr(output, "logits", None) is not None
                else None
            )
            (loss / GRAD_ACCUM).backward()
            gradients.append(loss_value)
            processed += 1
            consecutive_errors = 0
            del output, batch, loss
            if len(gradients) < GRAD_ACCUM:
                continue
            grad_norm = torch.nn.utils.clip_grad_norm_(
                (p for p in model.parameters() if p.requires_grad),
                1.0,
            )
            optimizer.step()
            optimizer.zero_grad(set_to_none=True)
            now = time.perf_counter()
            completed += 1
            step_seconds = now - start_step
            start_step = now
            last_step_time = step_seconds
            metric = {
                "time": datetime.now(UTC).isoformat(),
                "optimizer_step": completed,
                "processed_samples": processed,
                "mean_loss": sum(gradients) / len(gradients),
                "gradient_norm": float(grad_norm.cpu()),
                "step_seconds": step_seconds,
                "seconds_per_sample": step_seconds / len(gradients),
                "peak_gpu_memory_gib": torch.cuda.max_memory_allocated()
                / 1024**3,
            }
            gradients.clear()
            with metrics_file.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(metric, ensure_ascii=False) + "\n")
            print(json.dumps(metric, ensure_ascii=False), flush=True)
            should_validate = (
                VALIDATION_EVERY_STEPS > 0
                and (
                    completed % VALIDATION_EVERY_STEPS == 0
                    or completed >= target_steps
                )
            )
            if (
                EVAL_STEP > 0
                and VALIDATION_EVERY_STEPS > 0
                and completed != target_steps
                and completed % VALIDATION_EVERY_STEPS == 0
            ):
                # The fixed hot-start checkpoint is external selection metadata,
                # not a baseline for comparing the internal validation stream.
                best_validation_loss = float("inf")
                EVAL_STEP = 0
            if should_validate:
                validation = _evaluate_validation(
                    model,
                    processor,
                    validation_rows,
                    torch=torch,
                    Image=Image,
                    max_rows=VALIDATION_LIMIT,
                )
                metric["validation_loss"] = validation["loss"]
                with metrics_file.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(metric, ensure_ascii=False) + "\n")
                _write_json(
                    run_dir / f"validation-step-{completed:06d}.json", validation
                )
                validation_loss = validation["loss"]
                improved = (
                    validation_loss is not None
                    and validation_loss < best_validation_loss
                )
                if improved:
                    best_validation_loss = validation_loss
                    stale_validations = 0
                    best_step = completed
                    best_checkpoint_path = (
                        run_dir / "checkpoints" / f"step-{completed:06d}"
                    )
                    best_source = "training"
                else:
                    stale_validations += 1
                save_checkpoint(
                    completed,
                    validation_loss,
                    current_best=best_step,
                    current_best_loss=best_validation_loss,
                )
                if stale_validations >= EARLY_STOPPING_PATIENCE:
                    truncated_reason = "early_stopping"
                    break
            elif SAVE_EVERY_STEPS > 0 and completed % SAVE_EVERY_STEPS == 0:
                save_checkpoint(completed, None)
            if completed >= target_steps:
                truncated_reason = "step_budget"
                break
        except torch.cuda.OutOfMemoryError:
            skipped += 1
            consecutive_errors += 1
            torch.cuda.empty_cache()
            gc.collect()
            optimizer.zero_grad(set_to_none=True)
            gradients.clear()
            print(
                f"Skipped OOM {image_path} "
                f"({consecutive_errors}/{MAX_CONSECUTIVE_ERRORS})",
                flush=True,
            )
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                truncated_reason = "fatal_sample_errors"
                break
        except Exception as exc:
            skipped += 1
            consecutive_errors += 1
            optimizer.zero_grad(set_to_none=True)
            gradients.clear()
            adapter_grads = [
                parameter.grad
                for name, parameter in model.named_parameters()
                if "lora_" in name and parameter.requires_grad
            ]
            last_error = {
                "time": datetime.now(UTC).isoformat(),
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(limit=12),
                "image_path": image_path,
                "task": row["task"],
                "label": row["label"],
                "sequence_tokens": (
                    int(image_batch["input_ids"].shape[1])
                    if image_batch is not None
                    else None
                ),
                "pixel_shape": (
                    list(image_batch["pixel_values"].shape)
                    if image_batch is not None and "pixel_values" in image_batch
                    else None
                ),
                "pixel_dtype": (
                    str(image_batch["pixel_values"].dtype)
                    if image_batch is not None and "pixel_values" in image_batch
                    else None
                ),
                "loss_requires_grad": loss_requires_grad,
                "logits_requires_grad": logits_requires_grad,
                "gradient_parameters": sum(
                    parameter.numel()
                    for parameter in model.parameters()
                    if parameter.requires_grad
                ),
                "adapter_grad_tensors": len(adapter_grads),
                "adapter_non_null_grads": sum(
                    gradient is not None for gradient in adapter_grads
                ),
            }
            _write_json(run_dir / "failure_diagnostic.json", last_error)
            print(
                f"Skipped {image_path}: {type(exc).__name__}: {exc} "
                f"({consecutive_errors}/{MAX_CONSECUTIVE_ERRORS})",
                flush=True,
            )
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                truncated_reason = "fatal_sample_errors"
                break
        finally:
            if source is not None:
                source.close()
    optimizer.zero_grad(set_to_none=True)
    if completed:
        final_checkpoint_dir = run_dir / "checkpoints" / f"step-{completed:06d}"
        if not final_checkpoint_dir.is_dir():
            save_checkpoint(completed, None)
        if best_step == 0:
            best_step = completed
            best_checkpoint_path = final_checkpoint_dir
        _write_json(
            run_dir / "last_checkpoint.json",
            {
                "checkpoint_dir": str(final_checkpoint_dir),
                "optimizer_step": completed,
                "processed_samples": processed,
                "skipped_samples": skipped,
                "attempted_samples": attempted,
                "stop_reason": truncated_reason,
            },
        )

    adapter_dir = run_dir / "final_adapter"
    if best_step or initial_adapter is not None:
        best_checkpoint_dir = best_checkpoint_path
        best_adapter_dir = run_dir / "best_adapter"
        best_adapter_dir.mkdir(parents=True, exist_ok=True)
        for name in ("adapter_config.json", "adapter_model.safetensors"):
            source = best_checkpoint_dir / name
            if not source.is_file():
                raise FileNotFoundError(source)
            shutil.copy2(source, best_adapter_dir / name)
        _write_json(
            best_adapter_dir / "adapter_manifest.json",
            {
                "run_id": RUN_ID,
                "source_checkpoint": str(best_checkpoint_dir),
                "best_step": best_step,
                "best_source": best_source,
                "selection_criterion": (
                    "fixed external holdout choice, then lowest training "
                    "validation loss; new holdout evaluation runs separately"
                ),
                "paired_selection_sha256": PAIRED_SELECTION_SHA256,
                "adapter_sha256": {
                    name: _sha256(best_adapter_dir / name)
                    for name in (
                        "adapter_config.json",
                        "adapter_model.safetensors",
                    )
                },
            },
        )
        processor.save_pretrained(run_dir / "processor")
        model.save_pretrained(adapter_dir)
        _write_json(
            run_dir / "best_checkpoint.json",
            {
                "step": best_step,
                "validation_loss": best_validation_loss,
                "checkpoint_dir": str(best_checkpoint_dir),
                "source": best_source,
                "adapter_dir": str(best_adapter_dir),
                "note": (
                    "best_adapter contains only the latest validated LoRA adapter "
                    "weights; test-set selection runs in a separate evaluator; "
                    "final_adapter represents the last in-memory step and is "
                    "not the default deployment artifact."
                ),
            },
        )
    elapsed = time.perf_counter() - timer
    if truncated_reason == "fatal_sample_errors":
        status = "failed"
    elif completed and truncated_reason in {"step_budget", "wall_clock_budget"}:
        status = "calibration_completed"
    elif completed:
        status = "completed"
    else:
        status = "no_optimizer_step"
    metrics = {
        "status": status,
        "run_kind": RUN_KIND,
        "run_id": RUN_ID,
        "resume_requested": RESUME,
        "resumed_from_step": resumed_from_step,
        "initial_adapter": initial_adapter,
        "best_step": best_step,
        "best_source": best_source,
        "paired_eval": best_metrics,
        "selection_criterion": (
            "fixed external holdout choice, then lowest training validation "
            "loss; new holdout evaluation runs separately"
        ),
        "target_step": target_steps,
        "optimizer_steps": completed,
        "processed_samples": processed,
        "skipped_samples": skipped,
        "attempted_samples": attempted,
        "consecutive_errors_at_stop": consecutive_errors,
        "stop_reason": (
            "in_memory_best"
            if completed < target_steps and validation_rows
            else truncated_reason
        ),
        "budget_truncated": truncated_reason
        in {"step_budget", "wall_clock_budget"},
        "elapsed_seconds": elapsed,
        "peak_gpu_memory_gib": torch.cuda.max_memory_allocated() / 1024**3,
        "gpu_name": torch.cuda.get_device_name(0),
        "finished_at": datetime.now(UTC).isoformat(),
        "adapter_dir": str(run_dir / "best_adapter" if best_step else adapter_dir),
        "best_checkpoint": str(
            run_dir / "checkpoints" / f"step-{best_step:06d}"
        ),
        "best_validation_loss": best_validation_loss,
        "holdout_evaluated": bool(best_metrics),
        "last_error": last_error,
    }
    _write_json(run_dir / "train_summary.json", metrics)
    (run_dir / "model_card.md").write_text(
        "# Qwen3.5-4B stage-one QLoRA\n\n"
        "- Base: Qwen/Qwen3.5-4B, 4-bit NF4.\n"
        "- Data: stage-one task subset with deterministic validation.\n"
        "- The hot-start checkpoint and any later checkpoint both use the\n"
        "  fixed 40-row holdout, which was evaluated outside training.\n"
        "- Training validation loss controls continuation and early stopping.\n"
        "- The test set was never used for gradient updates.\n"
        "- Limitation: this run does not establish clinical validity. "
        "Every output requires human review.\n",
        encoding="utf-8",
    )
    runs_volume.commit()
    _write_json(
        run_dir / "modal_launch.json",
        {
            "function": "train",
            "run_id": RUN_ID,
            "resume": RESUME,
            "train_limit": TRAIN_LIMIT,
            "grad_accum": GRAD_ACCUM,
            "validation_every_steps": VALIDATION_EVERY_STEPS,
            "validation_limit": VALIDATION_LIMIT,
            "save_every_steps": SAVE_EVERY_STEPS,
            "max_minutes": MAX_MINUTES,
            "max_steps": MAX_STEPS,
            "max_pixels": MAX_PIXELS,
            "max_length": MAX_LENGTH,
            "learning_rate": LEARNING_RATE,
            "focus01": FOCUS01,
            "init_run_id": INIT_RUN_ID,
            "init_step": INIT_STEP,
            "container_timeout_seconds": 5 * 60 * 60,
            "paired_selection_sha256": PAIRED_SELECTION_SHA256,
            "cyclic": CYCLIC,
            "eval_step": EVAL_STEP,
        },
    )
    return json.dumps(metrics, indent=2, ensure_ascii=False)


@app.local_entrypoint()
def main() -> None:
    option_names = {
        "run_id": "UV_RUN_ID",
        "run_kind": "UV_RUN_KIND",
        "train_limit": "UV_TRAIN_LIMIT",
        "max_steps": "UV_MAX_STEPS",
        "max_minutes": "UV_MAX_MINUTES",
        "max_pixels": "UV_MAX_PIXELS",
        "max_length": "UV_MAX_LENGTH",
        "grad_accum": "UV_GRAD_ACCUM",
        "save_every_steps": "UV_SAVE_EVERY_STEPS",
        "validation_every_steps": "UV_VALIDATION_EVERY_STEPS",
        "validation_limit": "UV_VALIDATION_LIMIT",
        "early_stopping_patience": "UV_EARLY_STOPPING_PATIENCE",
        "max_consecutive_errors": "UV_MAX_CONSECUTIVE_ERRORS",
        "resume": "UV_RESUME",
        "init_run_id": "UV_INIT_RUN_ID",
        "init_step": "UV_INIT_STEP",
        "focus01": "UV_FOCUS01",
        "learning_rate": "UV_LEARNING_RATE",
        "paired_selection_sha256": "UV_PAIRED_SELECTION_SHA256",
        "cyclic": "UV_CYCLIC",
        "eval_step": "UV_EVAL_STEP",
    }
    options = {
        key: os.environ[environment_name]
        for key, environment_name in option_names.items()
        if environment_name in os.environ
    }
    print(train.remote(options))

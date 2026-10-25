"""Evaluate a Qwen3.5-4B QLoRA adapter on the frozen manifest test split.

Run from the repository root:

    $env:HTTP_PROXY = ""
    $env:HTTPS_PROXY = ""
    $env:ALL_PROXY = ""
    $env:UV_RUN_ID = "qwen4b-stage1-..."
    $env:UV_EVAL_LIMIT = "50"
    .\.venv-modal\Scripts\modal.exe run model-training\code\training\modal_qwen4b_eval.py

The evaluator loads the base model plus the run's final adapter, never trains
on test rows, and writes per-task metrics and raw generations to uveitis-runs.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import random
import re
import shutil
import tempfile
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

import modal

from modal_volumes import (
    DATA_ROOT,
    EVAL_TASK_LIMITS,
    MANIFEST_PATH,
    PHASE1_TASKS,
    QWEN4B_SUBDIR,
    RUNS_VOLUME_NAME,
    TASK_LABELS,
    data_volume,
    models_volume,
    runs_volume,
)


APP_NAME = "uveitis-qwen4b-eval"
MODEL_PATH = f"/models/{QWEN4B_SUBDIR}"
RUN_ID = os.environ.get("UV_RUN_ID", "")
RUN_ROOT = f"/runs/qwen3.5-4b/{RUN_ID}" if RUN_ID else ""
EVAL_LIMIT = int(os.environ.get("UV_EVAL_LIMIT", "40"))
EVAL_OUTPUT_DIR = os.environ.get("UV_EVAL_OUTPUT_DIR", "")
PAIRED_RUN_ID = os.environ.get("UV_PAIRED_RUN_ID", "")
REQUIRED_SELECTION_SHA256 = os.environ.get(
    "UV_REQUIRED_SELECTION_SHA256", ""
)
MAX_PIXELS = int(os.environ.get("UV_MAX_PIXELS", str(448 * 448)))
MAX_NEW_TOKENS = int(os.environ.get("UV_MAX_NEW_TOKENS", "64"))
BASELINE = os.environ.get("UV_EVAL_BASELINE", "0").lower() in {"1", "true"}
CHECKPOINT_STEP = os.environ.get("UV_CHECKPOINT_STEP", "")
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


def _balanced_rows(
    rows: list[dict], task_limits: dict[str, int], seed: int
) -> list[dict]:
    grouped: dict[str, dict[str, list[dict]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in rows:
        grouped[row["task"]][row["label"]].append(dict(row))
    rng = random.Random(seed)
    for labels in grouped.values():
        for values in labels.values():
            values.sort(key=lambda item: item["image"])
            rng.shuffle(values)
    chosen: list[dict] = []
    for task in PHASE1_TASKS:
        labels = grouped[task]
        positions = {label: 0 for label in labels}
        task_count = 0
        while task_count < task_limits.get(task, 0):
            added = False
            for label in sorted(labels):
                index = positions[label]
                if index < len(labels[label]):
                    chosen.append(labels[label][index])
                    positions[label] += 1
                    task_count += 1
                    added = True
                    if task_count >= task_limits.get(task, 0):
                        break
            if not added:
                break
    return chosen


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _selection_sha256(rows: list[dict]) -> str:
    """Identify the exact holdout set independently of model metrics."""
    keys = sorted(
        f"{row['task']}\t{row['image']}\t{row['label']}" for row in rows
    )
    return hashlib.sha256("\n".join(keys).encode("utf-8")).hexdigest()


def _image_path(row: dict) -> str:
    return f"{DATA_ROOT}/{row['dataset']}/{row['source_image']}"


def _prompt(task: str) -> str:
    labels = TASK_LABELS[task]
    return (
        "Classify this retinal image. Do not infer any finding that is not "
        f"visible. Task: {task}. Allowed labels: {json.dumps(labels)}. "
        "Choose exactly one allowed label and return only compact JSON with "
        '{"label":"...","requires_human_review":true}.'
    )


def _parse_label(text: str, task: str) -> str | None:
    match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    label = payload.get("label")
    return label if label in TASK_LABELS[task] else None


def _metrics(labels: list[str], predictions: list[str | None]) -> dict:
    if not labels:
        return {"samples": 0, "accuracy": None, "macro_f1": None}
    classes = sorted(set(labels))
    per_class: dict[str, dict] = {}
    f1_scores: list[float] = []
    for label in classes:
        tp = sum(a == label and p == label for a, p in zip(labels, predictions))
        fp = sum(a != label and p == label for a, p in zip(labels, predictions))
        fn = sum(a == label and p != label for a, p in zip(labels, predictions))
        denominator = 2 * tp + fp + fn
        f1 = 2 * tp / denominator if denominator else 0.0
        f1_scores.append(f1)
        per_class[label] = {
            "precision": tp / (tp + fp) if tp + fp else 0.0,
            "recall": tp / (tp + fn) if tp + fn else 0.0,
            "f1": f1,
            "support": sum(a == label for a in labels),
        }
    matrix: dict[str, dict[str, int]] = {}
    for actual in sorted(set(labels)):
        matrix[actual] = {}
        for predicted in sorted(classes):
            matrix[actual][predicted] = sum(
                a == actual and p == predicted
                for a, p in zip(labels, predictions)
            )
    return {
        "samples": len(labels),
        "accuracy": sum(a == p for a, p in zip(labels, predictions)) / len(labels),
        "macro_f1": sum(f1_scores) / len(f1_scores),
        "json_valid_rate": sum(p is not None for p in predictions) / len(labels),
        "per_class": per_class,
        "confusion_matrix": matrix,
    }


def _save_adapter(model, output_dir: Path) -> None:
    model.save_pretrained(output_dir)


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
    timeout=2 * 60 * 60,
    max_containers=1,
)
def evaluate(options: dict | None = None) -> str:
    global RUN_ID, RUN_ROOT, EVAL_LIMIT, MAX_PIXELS, MAX_NEW_TOKENS, BASELINE
    global CHECKPOINT_STEP, EVAL_OUTPUT_DIR
    options = options or {}
    RUN_ID = str(options.get("run_id", RUN_ID))
    RUN_ROOT = f"/runs/qwen3.5-4b/{RUN_ID}"
    EVAL_LIMIT = int(options.get("eval_limit", EVAL_LIMIT))
    EVAL_OUTPUT_DIR = str(options.get("output_dir", EVAL_OUTPUT_DIR))
    MAX_PIXELS = int(options.get("max_pixels", MAX_PIXELS))
    MAX_NEW_TOKENS = int(options.get("max_new_tokens", MAX_NEW_TOKENS))
    BASELINE = str(options.get("baseline", "0")).lower() in {"1", "true"}
    CHECKPOINT_STEP = str(options.get("checkpoint_step", CHECKPOINT_STEP))

    if not RUN_ID:
        raise ValueError("UV_RUN_ID is required")
    import torch
    from PIL import Image
    from peft import PeftModel
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
    run_dir = Path(RUN_ROOT)
    adapter_dir = (
        run_dir / "checkpoints" / f"step-{int(CHECKPOINT_STEP):06d}"
        if CHECKPOINT_STEP
        else run_dir / "best_adapter"
    )
    if not BASELINE and not (adapter_dir / "adapter_config.json").is_file():
        raise FileNotFoundError(adapter_dir / "adapter_config.json")

    with open(MANIFEST_PATH, "r", encoding="utf-8", newline="") as handle:
        rows = [
            row
            for row in csv.DictReader(handle)
            if row["task"] in PHASE1_TASKS and row["split"] == "test"
        ]
    task_count = len(PHASE1_TASKS)
    if "eval_limit" in options or not PAIRED_RUN_ID:
        task_limits = {
            "oct_uveitis_4class": 10,
            "fundus_toxo_binary": 10,
            "eye_five_class": 10,
            "oct_aux_4class": 10,
        }
    else:
        task_limits = dict(EVAL_TASK_LIMITS)
    selected = _balanced_rows(rows, task_limits, SEED)
    rng = random.Random(SEED)
    rng.shuffle(selected)
    output_dir = (
        run_dir / EVAL_OUTPUT_DIR.strip("/") if EVAL_OUTPUT_DIR else run_dir
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    print(
        "Evaluation selection: "
        + json.dumps(
            dict(Counter(f"{row['task']}::{row['label']}" for row in selected)),
            ensure_ascii=False,
        ),
        flush=True,
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
    if not BASELINE:
        adapter_load_dir = adapter_dir
        if (adapter_dir / "training_state.pt").is_file():
            adapter_load_dir = Path(tempfile.mkdtemp(prefix="adapter-only-"))
            for name in ("adapter_config.json", "adapter_model.safetensors"):
                shutil.copy2(adapter_dir / name, adapter_load_dir / name)
        model = PeftModel.from_pretrained(model, adapter_load_dir)
    model.eval()

    outputs: list[dict] = []
    for row in selected:
        task = row["task"]
        try:
            image_obj = Image.open(_image_path(row)).convert("RGB")
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": image_obj},
                        {"type": "text", "text": _prompt(task)},
                    ],
                }
            ]
            text = processor.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,
            )
            inputs = processor(
                text=[text],
                images=[image_obj],
                return_tensors="pt",
                max_pixels=MAX_PIXELS,
            )
            inputs = {
                key: value.to("cuda") if torch.is_tensor(value) else value
                for key, value in inputs.items()
            }
            with torch.inference_mode():
                generated = model.generate(
                    **inputs,
                    max_new_tokens=MAX_NEW_TOKENS,
                    do_sample=False,
                )
            generated = generated[:, inputs["input_ids"].shape[1] :]
            raw = processor.batch_decode(generated, skip_special_tokens=True)[0]
            predicted = _parse_label(raw, task)
            outputs.append(
                {
                    "image": row["image"],
                    "dataset": row["dataset"],
                    "task": task,
                    "expected": row["label"],
                    "predicted": predicted,
                    "raw": raw,
                }
            )
            image_obj.close()
            del inputs, generated
        except Exception as exc:
            outputs.append(
                {
                    "image": row["image"],
                    "dataset": row["dataset"],
                    "task": task,
                    "expected": row["label"],
                    "predicted": None,
                    "raw": "",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    print(
        "Selected evaluation buckets: "
        + json.dumps(
            dict(
                Counter(
                    f"{row['task']}::{row['label']}" for row in selected
                )
            ),
            ensure_ascii=False,
        ),
        flush=True,
    )

    task_metrics = {}
    selected_counts = Counter(
        f"{item['task']}::{item['expected']}" for item in outputs
    )
    for task in PHASE1_TASKS:
        task_rows = [item for item in outputs if item["task"] == task]
        task_metrics[task] = _metrics(
            [item["expected"] for item in task_rows],
            [item["predicted"] for item in task_rows],
        )
        task_metrics[task]["errors"] = sum("error" in item for item in task_rows)
    metrics = {
        "run_id": RUN_ID,
        "checkpoint_step": int(CHECKPOINT_STEP) if CHECKPOINT_STEP else None,
        "evaluation_type": "zero_shot_base" if BASELINE else "qlora_adapter",
        "rows": len(outputs),
        "tasks": task_metrics,
        "elapsed_seconds": time.perf_counter() - timer,
        "peak_gpu_memory_gib": torch.cuda.max_memory_allocated() / 1024**3,
        "finished_at": datetime.now(UTC).isoformat(),
        "note": (
            "Only the frozen manifest test split was evaluated. "
            "03 is prototype data; outputs require human review."
        ),
    }
    selection_sha256 = _selection_sha256(selected)
    if REQUIRED_SELECTION_SHA256 and selection_sha256 != REQUIRED_SELECTION_SHA256:
        raise ValueError(
            "Paired evaluation selected different rows; refusing to compare metrics"
        )
    output_name = "baseline_metrics.json" if BASELINE else "eval_metrics.json"
    _write_json(output_dir / output_name, metrics)
    _write_json(output_dir / "eval_predictions.json", outputs)
    _write_json(
        output_dir / "eval_manifest.json",
        {
            "run_id": RUN_ID,
            "limit": EVAL_LIMIT,
            "baseline": BASELINE,
            "checkpoint_step": int(CHECKPOINT_STEP) if CHECKPOINT_STEP else None,
            "tasks": list(PHASE1_TASKS),
            "test_rows": len(rows),
            "balance": "round_robin_by_task_and_label",
            "evaluated_rows": len(outputs),
            "evaluated_label_counts": dict(selected_counts),
            "selection_sha256": selection_sha256,
            "output_dir": str(output_dir),
            "started_at": started.isoformat(),
        },
    )
    runs_volume.commit()
    return json.dumps(metrics, ensure_ascii=False)


@app.local_entrypoint()
def main() -> None:
    names = {
        "run_id": "UV_RUN_ID",
        "eval_limit": "UV_EVAL_LIMIT",
        "max_pixels": "UV_MAX_PIXELS",
        "max_new_tokens": "UV_MAX_NEW_TOKENS",
        "baseline": "UV_EVAL_BASELINE",
        "checkpoint_step": "UV_CHECKPOINT_STEP",
        "output_dir": "UV_EVAL_OUTPUT_DIR",
    }
    options = {
        key: os.environ[name] for key, name in names.items() if name in os.environ
    }
    print(evaluate.remote(options))

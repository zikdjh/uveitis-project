"""Evaluate local Qwen3.5-4B adapters on the frozen manifest test split.

Predictions are appended to a partial JSONL file after each sample, so a long
local evaluation can be resumed without rerunning completed images. The
evaluator never uses test rows for training or checkpoint selection.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from local_qwen4b_smoke import (
    MANIFEST_PATH,
    MODEL_DIR,
    PHASE1_TASKS,
    ROOT,
    TASK_LABELS,
    _image_path,
    _sha256,
    _write_json,
)


def _selection_sha256(rows: list[dict]) -> str:
    keys = sorted(
        f"{row['task']}\t{row['image']}\t{row['label']}" for row in rows
    )
    return hashlib.sha256("\n".join(keys).encode("utf-8")).hexdigest()


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
    for actual in classes:
        matrix[actual] = {
            predicted: sum(
                a == actual and p == predicted
                for a, p in zip(labels, predictions)
            )
            for predicted in classes
        }
    return {
        "samples": len(labels),
        "accuracy": sum(a == p for a, p in zip(labels, predictions)) / len(labels),
        "macro_f1": sum(f1_scores) / len(f1_scores),
        "json_valid_rate": sum(p is not None for p in predictions) / len(labels),
        "per_class": per_class,
        "confusion_matrix": matrix,
    }


def _load_test_rows(tasks: set[str]) -> list[dict]:
    with MANIFEST_PATH.open("r", encoding="utf-8", newline="") as handle:
        rows = [
            dict(row)
            for row in csv.DictReader(handle)
            if row["split"] == "test" and row["task"] in tasks
        ]
    if not rows:
        raise ValueError(f"No frozen test rows found for tasks={sorted(tasks)}")
    missing = [row["image"] for row in rows if not _image_path(row).is_file()]
    if missing:
        raise FileNotFoundError(
            f"{len(missing)} evaluation images are missing; first={missing[0]}"
        )
    rows.sort(key=lambda row: (row["task"], row["image"]))
    return rows


def _prediction_key(item: dict) -> str:
    return f"{item['task']}\t{item['image']}"


def _read_partial(path: Path) -> dict[str, dict]:
    completed: dict[str, dict] = {}
    if not path.is_file():
        return completed
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                print(
                    json.dumps(
                        {
                            "event": "resume_skip_invalid_line",
                            "line": line_number,
                        }
                    ),
                    flush=True,
                )
                continue
            completed[_prediction_key(item)] = item
    return completed


def _write_prediction(handle, item: dict) -> None:
    handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    handle.flush()


def _summarize(
    rows: list[dict],
    predictions_by_key: dict[str, dict],
    *,
    tasks: list[str],
    adapter_dir: Path,
    output_dir: Path,
    selection_sha256: str,
    started_at: datetime,
    elapsed_seconds: float,
    torch,
    max_new_tokens: int,
    image_pixels: int,
) -> dict:
    outputs = [
        predictions_by_key[_prediction_key({"task": row["task"], "image": row["image"]})]
        for row in rows
    ]
    task_metrics = {}
    for task in tasks:
        task_rows = [item for item in outputs if item["task"] == task]
        task_metrics[task] = _metrics(
            [item["expected"] for item in task_rows],
            [item["predicted"] for item in task_rows],
        )
        task_metrics[task]["errors"] = sum("error" in item for item in task_rows)

    metrics = {
        "status": "ok",
        "adapter_dir": str(adapter_dir),
        "adapter_sha256": _sha256(adapter_dir / "adapter_model.safetensors"),
        "manifest_sha256": _sha256(MANIFEST_PATH),
        "selection_sha256": selection_sha256,
        "tasks": task_metrics,
        "rows": len(outputs),
        "evaluated_label_counts": dict(
            sorted(Counter(f"{item['task']}::{item['expected']}" for item in outputs).items())
        ),
        "generation": {
            "max_new_tokens": max_new_tokens,
            "image_pixels": image_pixels,
            "do_sample": False,
        },
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "elapsed_seconds": elapsed_seconds,
        "peak_allocated_gib": (
            torch.cuda.max_memory_allocated() / 1024**3
            if torch and torch.cuda.is_initialized()
            else None
        ),
        "peak_reserved_gib": (
            torch.cuda.max_memory_reserved() / 1024**3
            if torch and torch.cuda.is_initialized()
            else None
        ),
        "note": (
            "Only the frozen manifest test split was evaluated. "
            "01 is not patient-isolated; 03 contains prototype/augmentation "
            "relationships. Human review remains required."
        ),
    }
    _write_json(output_dir / "eval_metrics.json", metrics)
    _write_json(
        output_dir / "predictions.json",
        outputs,
    )
    _write_json(
        output_dir / "eval_manifest.json",
        {
            "adapter_dir": str(adapter_dir),
            "adapter_sha256": metrics["adapter_sha256"],
            "tasks": tasks,
            "rows": len(outputs),
            "selection_sha256": selection_sha256,
            "partial_predictions": "predictions.partial.jsonl",
            "output_dir": str(output_dir),
        },
    )
    _write_json(
        output_dir / "eval_summary.json",
        {
            "status": "ok",
            "adapter_sha256": metrics["adapter_sha256"],
            "selection_sha256": selection_sha256,
            "tasks": tasks,
            "rows": len(outputs),
            "elapsed_seconds": elapsed_seconds,
            "metrics": "eval_metrics.json",
            "predictions": "predictions.json",
        },
    )
    return metrics


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--task", action="append", default=[])
    parser.add_argument("--max-new-tokens", type=int, default=32)
    parser.add_argument("--image-pixels", type=int, default=65_536)
    parser.add_argument("--max-samples", type=int)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    tasks = args.task or ["oct_aux_4class"]
    unknown = set(tasks) - PHASE1_TASKS
    if unknown:
        raise ValueError(f"Unknown tasks: {sorted(unknown)}")
    if not 8 <= args.max_new_tokens <= 128:
        raise ValueError("--max-new-tokens must be between 8 and 128")
    if not 4_096 <= args.image_pixels <= 451_584:
        raise ValueError("--image-pixels must be between 4096 and 451584")
    if not MODEL_DIR.is_dir() or not MANIFEST_PATH.is_file():
        raise FileNotFoundError("Local model or manifest is missing")
    if not (args.adapter_dir / "adapter_config.json").is_file():
        raise FileNotFoundError(args.adapter_dir / "adapter_config.json")
    if not (args.adapter_dir / "adapter_model.safetensors").is_file():
        raise FileNotFoundError(args.adapter_dir / "adapter_model.safetensors")

    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    rows = _load_test_rows(set(tasks))
    if args.max_samples is not None:
        if args.max_samples < 1:
            raise ValueError("--max-samples must be positive")
        rows = rows[: args.max_samples]
    selection_sha256 = _selection_sha256(rows)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    partial_path = output_dir / "predictions.partial.jsonl"
    if args.overwrite and partial_path.exists():
        partial_path.unlink()

    started_at = datetime.now(UTC)
    timer = time.perf_counter()
    completed = _read_partial(partial_path)
    missing_rows = [
        row for row in rows if _prediction_key(row) not in completed
    ]
    remaining_rows = [
        row
        for row in missing_rows
        if _prediction_key(row) not in completed
    ]
    print(
        json.dumps(
            {
                "event": "evaluation_plan",
                "adapter_dir": str(args.adapter_dir.resolve()),
                "output_dir": str(output_dir),
                "tasks": tasks,
                "total_rows": len(rows),
                "completed_rows": len(rows) - len(remaining_rows),
                "remaining_rows": len(remaining_rows),
                "selection_sha256": selection_sha256,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    torch = None
    if remaining_rows:
        import torch as torch_module
        from PIL import Image
        from peft import PeftModel
        from transformers import (
            AutoModelForImageTextToText,
            AutoProcessor,
            BitsAndBytesConfig,
        )

        torch = torch_module
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is not available")
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
        base_model = AutoModelForImageTextToText.from_pretrained(
            MODEL_DIR,
            local_files_only=True,
            quantization_config=quantization,
            torch_dtype=torch.bfloat16,
            device_map={"": 0},
            attn_implementation="sdpa",
            low_cpu_mem_usage=True,
        )
        model = PeftModel.from_pretrained(
            base_model,
            str(args.adapter_dir.resolve()),
            is_trainable=False,
        )
        model.eval()
        print(
            json.dumps(
                {
                    "event": "adapter_loaded",
                    "allocated_gib": torch.cuda.memory_allocated() / 1024**3,
                    "reserved_gib": torch.cuda.memory_reserved() / 1024**3,
                }
            ),
            flush=True,
        )
        completed_this_run = 0
        with partial_path.open("a", encoding="utf-8") as handle:
            for row in remaining_rows:
                item_started = time.perf_counter()
                try:
                    image_obj = Image.open(_image_path(row)).convert("RGB")
                    messages = [
                        {
                            "role": "user",
                            "content": [
                                {"type": "image", "image": image_obj},
                                {
                                    "type": "text",
                                    "text": _prompt(row["task"]),
                                },
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
                        size={
                            "shortest_edge": args.image_pixels,
                            "longest_edge": args.image_pixels,
                        },
                    )
                    inputs = {
                        key: value.to("cuda") if torch.is_tensor(value) else value
                        for key, value in inputs.items()
                    }
                    with torch.inference_mode():
                        generated = model.generate(
                            **inputs,
                            max_new_tokens=args.max_new_tokens,
                            do_sample=False,
                        )
                    generated = generated[:, inputs["input_ids"].shape[1] :]
                    raw = processor.batch_decode(
                        generated,
                        skip_special_tokens=True,
                    )[0]
                    item = {
                        "task": row["task"],
                        "dataset": row["dataset"],
                        "image": row["image"],
                        "expected": row["label"],
                        "predicted": _parse_label(raw, row["task"]),
                        "raw": raw,
                        "elapsed_seconds": time.perf_counter() - item_started,
                    }
                    image_obj.close()
                    del inputs, generated
                except Exception as exc:
                    item = {
                        "task": row["task"],
                        "dataset": row["dataset"],
                        "image": row["image"],
                        "expected": row["label"],
                        "predicted": None,
                        "raw": "",
                        "error": f"{type(exc).__name__}: {exc}",
                        "elapsed_seconds": time.perf_counter() - item_started,
                    }
                _write_prediction(handle, item)
                completed[_prediction_key(item)] = item
                completed_this_run += 1
                if completed_this_run % 25 == 0:
                    elapsed = time.perf_counter() - timer
                    print(
                        json.dumps(
                            {
                                "event": "evaluation_progress",
                                "completed_this_run": completed_this_run,
                                "remaining_rows": len(remaining_rows) - completed_this_run,
                                "elapsed_seconds": elapsed,
                                "seconds_per_sample": elapsed / completed_this_run,
                                "peak_allocated_gib": (
                                    torch.cuda.max_memory_allocated() / 1024**3
                                ),
                                "peak_reserved_gib": (
                                    torch.cuda.max_memory_reserved() / 1024**3
                                ),
                            }
                        ),
                        flush=True,
                    )

    metrics = _summarize(
        rows,
        completed,
        tasks=tasks,
        adapter_dir=args.adapter_dir.resolve(),
        output_dir=output_dir,
        selection_sha256=selection_sha256,
        started_at=started_at,
        elapsed_seconds=time.perf_counter() - timer,
        torch=torch,
        max_new_tokens=args.max_new_tokens,
        image_pixels=args.image_pixels,
    )
    print(json.dumps(metrics, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

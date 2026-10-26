"""Evaluate a frozen local Qwen3.5-4B adapter on a patient-isolated task.

This is a research evaluation, not a clinical deployment check. Run it once
after checkpoint selection; test outputs must not be used for further tuning.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from local_qwen4b_smoke import ARTIFACTS_ROOT, MODEL_DIR, _sha256, _write_json
from local_qwen4b_train import _validate


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--image-pixels", type=int, default=16_384)
    parser.add_argument("--max-length", type=int, default=256)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    manifest = args.manifest.resolve()
    adapter = args.adapter.resolve()
    run_dir = ARTIFACTS_ROOT / args.run_id
    adapter_weights = adapter / "adapter_model.safetensors"
    if not manifest.is_file():
        raise FileNotFoundError(manifest)
    if not adapter_weights.is_file():
        raise FileNotFoundError(adapter_weights)
    if run_dir.exists():
        raise FileExistsError(f"Evaluation directory already exists: {run_dir}")
    if not 4_096 <= args.image_pixels <= 451_584:
        raise ValueError("--image-pixels must be between 4096 and 451584")
    if not 128 <= args.max_length <= 1024:
        raise ValueError("--max-length must be between 128 and 1024")

    with manifest.open("r", encoding="utf-8", newline="") as handle:
        rows = [
            dict(row)
            for row in csv.DictReader(handle)
            if row["split"] == "test" and row["task"] == args.task
        ]
    if not rows:
        raise ValueError("No test rows match the requested task")

    import torch
    from peft import PeftModel
    from PIL import Image
    from transformers import (
        AutoModelForImageTextToText,
        AutoProcessor,
        BitsAndBytesConfig,
    )

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available")
    if not torch.cuda.is_bf16_supported():
        raise RuntimeError("The local GPU does not support bfloat16")

    run_dir.mkdir(parents=True)
    started_at = datetime.now(UTC)
    timer = time.perf_counter()
    processor = AutoProcessor.from_pretrained(MODEL_DIR, local_files_only=True)
    quantization = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
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
        adapter,
        is_trainable=False,
    )
    model.eval()
    torch.cuda.reset_peak_memory_stats()
    metrics = _validate(
        model,
        processor,
        rows,
        torch=torch,
        Image=Image,
        image_pixels=args.image_pixels,
        max_length=args.max_length,
    )
    _write_json(run_dir / "predictions.json", metrics.pop("outputs"))
    result = {
        "status": "ok",
        "run_id": args.run_id,
        "task": args.task,
        "manifest": str(manifest),
        "manifest_sha256": _sha256(manifest),
        "adapter": str(adapter),
        "adapter_sha256": _sha256(adapter_weights),
        "test_rows_read": len(rows),
        "test_label_counts": dict(
            sorted(Counter(row["label"] for row in rows).items())
        ),
        "patient_groups": len({row["source_group"] for row in rows}),
        "image_pixels": args.image_pixels,
        "max_length": args.max_length,
        "metrics": metrics,
        "peak_allocated_gib": torch.cuda.max_memory_allocated() / 1024**3,
        "peak_reserved_gib": torch.cuda.max_memory_reserved() / 1024**3,
        "total_seconds": time.perf_counter() - timer,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "policy": (
            "Single evaluation of the validation-selected adapter. "
            "Do not tune hyperparameters or checkpoints from these test outputs."
        ),
        "clinical_status": "research_only_not_validated",
    }
    _write_json(run_dir / "evaluation.json", result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

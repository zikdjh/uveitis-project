"""Rank hard training groups with a frozen adapter without reading test images."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from local_qwen4b_smoke import (
    ARTIFACTS_ROOT,
    MANIFEST_PATH,
    MODEL_DIR,
    PHASE1_TASKS,
    ROOT,
    _build_prompt,
    _encode_example,
    _image_path,
    _sha256,
    _write_json,
)
from local_qwen4b_train import (
    DEFAULT_SEED,
    _audit_train_test_groups,
    _group_key,
    _load_phase1_test_rows,
    _load_phase1_train_rows,
    _split_validation,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-id",
        default="local-4060-oct-hard-groups-20261026-01",
    )
    parser.add_argument(
        "--adapter",
        type=Path,
        required=True,
        help="Frozen trainable-format adapter used for training-only loss scoring.",
    )
    parser.add_argument("--image-pixels", type=int, default=65_536)
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument("--validation-groups-per-class", type=int, default=3)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--target-groups", type=int, default=24)
    parser.add_argument("--max-weight", type=int, choices=(2, 3), default=2)
    parser.add_argument(
        "--from-groups",
        type=Path,
        help="Reuse groups.json from a completed scan instead of scoring again.",
    )
    parser.add_argument(
        "--include-other-tasks",
        action="store_true",
        help="Reserve up to 8 slots for hard non-OCT training groups.",
    )
    parser.add_argument("--weights-only", action="store_true")
    return parser.parse_args()


def _target_entries(
    scored_groups: list[dict],
    *,
    target_groups: int,
    max_weight: int,
    include_other_tasks: bool,
) -> list[dict]:
    oct_labels = ("CNV", "DME", "DRUSEN", "NORMAL")
    oct_quota = max(1, target_groups - 8) if include_other_tasks else target_groups
    targets: list[dict] = []
    selected: set[str] = set()
    per_class_quota = max(1, oct_quota // len(oct_labels))
    ranked_oct = sorted(
        (
            group
            for group in scored_groups
            if group["task"] == "oct_aux_4class"
        ),
        key=lambda item: (
            -item["errors"],
            -item["loss"],
            -item["samples"],
            item["group_key"],
        ),
    )
    for label in oct_labels:
        label_groups = [group for group in ranked_oct if group["label"] == label]
        for group in label_groups[:per_class_quota]:
            targets.append(group)
            selected.add(group["group_key"])
    for group in ranked_oct:
        if len(targets) >= oct_quota:
            break
        if group["group_key"] not in selected:
            targets.append(group)
            selected.add(group["group_key"])

    if include_other_tasks:
        other_groups = sorted(
            (
                group
                for group in scored_groups
                if group["task"] != "oct_aux_4class"
            ),
            key=lambda item: (
                -item["errors"],
                -item["loss"],
                -item["samples"],
                item["group_key"],
            ),
        )
        for group in other_groups:
            if len(targets) >= target_groups:
                break
            targets.append(group)
            selected.add(group["group_key"])

    if len(targets) < min(8, target_groups):
        raise RuntimeError("Too few grouped training errors to build difficulty weights")

    selected_groups = {entry["group_key"] for entry in targets}
    ranked = sorted(
        scored_groups,
        key=lambda item: (
            item["errors"] <= 0,
            -item["errors"],
            -item["loss"],
            item["group_key"],
        ),
    )
    for index, group in enumerate(ranked):
        if group["group_key"] not in selected_groups or group["errors"] <= 0:
            continue
        targets_by_key = next(
            item for item in targets if item["group_key"] == group["group_key"]
        )
        targets_by_key["weight"] = (
            max_weight
            if max_weight == 3 and index < max(1, len(targets) // 3)
            else 2
        )
    return targets


def main() -> None:
    args = _parse_args()
    if not MODEL_DIR.is_dir() or not MANIFEST_PATH.is_file():
        raise FileNotFoundError("Local model or manifest is missing")
    if not args.adapter.is_dir():
        raise FileNotFoundError(f"Adapter not found: {args.adapter}")
    if not 1 <= args.target_groups <= 96:
        raise ValueError("--target-groups must be between 1 and 96")

    output_dir = ARTIFACTS_ROOT / args.run_id
    if output_dir.exists():
        raise FileExistsError(f"Run directory already exists: {output_dir}")

    all_train = _load_phase1_train_rows(DEFAULT_MANIFEST_PATH)
    all_test = _load_phase1_test_rows(DEFAULT_MANIFEST_PATH)
    eligible_rows, split_audit = _audit_train_test_groups(all_train, all_test)
    train_rows, validation_rows = _split_validation(
        eligible_rows,
        validation_groups_per_class=args.validation_groups_per_class,
        seed=args.seed,
    )
    validation_groups = {_group_key(row) for row in validation_rows}
    train_groups = {_group_key(row) for row in train_rows}
    if validation_groups & train_groups:
        raise AssertionError("Training and validation groups overlap")
    if set(split_audit["datasets"]) and split_audit.get(
        "eligible_test_group_overlap"
    ) != 0:
        raise AssertionError("Eligible training groups overlap frozen test groups")

    adapter_path = args.adapter.resolve()
    adapter_sha256 = _sha256(adapter_path / "adapter_model.safetensors")
    output_dir.mkdir(parents=True)
    record: dict = {
        "status": "running",
        "started_at": datetime.now(UTC).isoformat(),
        "source_run": args.run_id,
        "adapter": str(adapter_path),
        "adapter_sha256": adapter_sha256,
        "manifest_sha256": _sha256(MANIFEST_PATH),
        "validation_selection_sha256": __import__(
            "local_qwen4b_train"
        )._rows_sha256(validation_rows),
        "configuration": {
            "image_pixels": args.image_pixels,
            "max_length": args.max_length,
            "validation_groups_per_class": args.validation_groups_per_class,
            "seed": args.seed,
            "target_groups": args.target_groups,
            "max_weight": args.max_weight,
            "include_other_tasks": args.include_other_tasks,
        },
        "audit": split_audit,
        "train_rows": len(train_rows),
        "validation_rows": len(validation_rows),
        "test_images_read": False,
    }

    reused = None
    if args.from_groups:
        reused = json.loads(args.from_groups.read_text(encoding="utf-8"))
        if reused.get("status") != "ok":
            raise ValueError("Source groups file is not complete")
        if reused.get("adapter_sha256") != adapter_sha256:
            raise ValueError("Source groups file was produced by another adapter")
        if reused.get("validation_selection_sha256") != record[
            "validation_selection_sha256"
        ]:
            raise ValueError("Source groups file uses another validation split")
        if reused.get("manifest_sha256") != record["manifest_sha256"]:
            raise ValueError("Source groups file uses another manifest")
        record["groups_scored"] = reused["groups_scored"]
        record["train_groups"] = reused["train_groups"]
        record["train_samples_scored"] = reused["train_samples_scored"]
        record["peak_reserved_gib"] = reused.get("peak_reserved_gib")

    if not args.weights_only and not args.from_groups:
        import torch
        from PIL import Image
        from peft import PeftModel
        from transformers import (
            AutoModelForImageTextToText,
            AutoProcessor,
            BitsAndBytesConfig,
        )

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is not available")
        processor = AutoProcessor.from_pretrained(
            MODEL_DIR,
            local_files_only=True,
        )
        model = AutoModelForImageTextToText.from_pretrained(
            MODEL_DIR,
            local_files_only=True,
            quantization_config=BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.bfloat16,
                bnb_4bit_use_double_quant=True,
            ),
            torch_dtype=torch.bfloat16,
            device_map={"": 0},
            attn_implementation="sdpa",
            low_cpu_mem_usage=True,
        )
        model = PeftModel.from_pretrained(
            model,
            str(adapter_path),
            is_trainable=True,
        )
        model.train()
        scored: list[dict] = []
        with torch.enable_grad():
            for index, row in enumerate(train_rows, start=1):
                prompt, answer = _build_prompt(row["task"], row["label"])
                with Image.open(_image_path(row)) as source:
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
                output = model(**batch)
                scored.append(
                    {
                        "group_key": _group_key(row),
                        "task": row["task"],
                        "label": row["label"],
                        "loss": float(output.loss.detach().cpu()),
                    }
                )
                del output, batch
                image.close()
                if index % 100 == 0:
                    print(
                        json.dumps(
                            {
                                "event": "difficulty_progress",
                                "completed": index,
                                "total": len(train_rows),
                                "peak_reserved_gib": (
                                    torch.cuda.max_memory_reserved() / 1024**3
                                ),
                            }
                        ),
                        flush=True,
                    )

        groups: dict[str, dict] = {}
        for item in scored:
            group = groups.setdefault(
                item["group_key"],
                {
                    "group_key": item["group_key"],
                    "task": item["task"],
                    "label": item["label"],
                    "samples": 0,
                    "errors": 0,
                    "loss_sum": 0.0,
                },
            )
            if group["group_key"] in validation_groups:
                raise AssertionError("Validation group was scored for training")
            group["samples"] += 1
            group["loss_sum"] += item["loss"]
            if item["loss"] >= 0.1:
                group["errors"] += 1
        scored_groups = []
        for group in groups.values():
            scored_groups.append(
                {
                    "group_key": group["group_key"],
                    "task": group["task"],
                    "label": group["label"],
                    "samples": group["samples"],
                    "errors": group["errors"],
                    "loss": group["loss_sum"] / group["samples"],
                }
            )
        scored_groups.sort(
            key=lambda item: (
                item["task"],
                -item["errors"],
                -item["loss"],
                item["group_key"],
            )
        )
        record["train_groups"] = len(scored_groups)
        record["train_samples_scored"] = len(scored)
        record["groups_scored"] = scored_groups
        record["peak_reserved_gib"] = torch.cuda.max_memory_reserved() / 1024**3
        del model
        torch.cuda.empty_cache()

    groups_path = output_dir / "groups.json"
    if groups_path.is_file():
        record["groups_scored"] = json.loads(
            groups_path.read_text(encoding="utf-8")
        )["groups_scored"]
    if "groups_scored" not in record:
        raise ValueError("No scored groups available for weights-only mode")

    targets = _target_entries(
        record["groups_scored"],
        target_groups=args.target_groups,
        max_weight=args.max_weight,
        include_other_tasks=args.include_other_tasks,
    )
    record["groups"] = targets
    record["weighted_class_exposures"] = {
        key: sum(entry["weight"] for entry in targets if entry["task"] == key)
        for key in sorted(PHASE1_TASKS)
    }
    record["status"] = "ok"
    record["finished_at"] = datetime.now(UTC).isoformat()
    _write_json(groups_path, record)
    _write_json(output_dir / "difficulty_manifest.json", record)
    print(
        json.dumps(
            {
                "status": record["status"],
                "output": str(output_dir),
                "groups": len(targets),
                "max_weight": max(entry["weight"] for entry in targets),
                "test_images_read": False,
            },
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()

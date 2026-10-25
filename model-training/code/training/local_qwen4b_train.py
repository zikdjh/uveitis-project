"""Run resumable QLoRA training for Qwen3.5-4B on the local RTX 4060.

The run uses only isolatable phase-one training rows. It audits manifest
metadata against the frozen test split, holds out whole image/source groups,
and selects checkpoints with generated-label metrics rather than teacher-forced
token loss alone. The exposure schedule balances task labels and rotates
through groups so a small source group cannot dominate a class.

This is a local stage-one training run, not a deployment promotion. Test-set
evaluation and human review remain separate steps.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import re
import shutil
import time
import traceback
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from local_qwen4b_smoke import (
    ARTIFACTS_ROOT,
    MANIFEST_PATH,
    MODEL_DIR,
    PHASE1_TASKS,
    ROOT,
    MemoryMonitor,
    _build_prompt,
    _encode_example,
    _image_path,
    _sha256,
    _write_json,
)


DEFAULT_SEED = 20261025


def _load_phase1_train_rows() -> list[dict]:
    with MANIFEST_PATH.open("r", encoding="utf-8", newline="") as handle:
        rows = [
            dict(row)
            for row in csv.DictReader(handle)
            if row["split"] == "train" and row["task"] in PHASE1_TASKS
        ]
    if not rows:
        raise ValueError("No phase-one train rows found")
    missing = [row["image"] for row in rows if not _image_path(row).is_file()]
    if missing:
        raise FileNotFoundError(
            f"{len(missing)} training images are missing; first={missing[0]}"
        )
    return rows


def _load_phase1_test_rows() -> list[dict]:
    with MANIFEST_PATH.open("r", encoding="utf-8", newline="") as handle:
        rows = [
            dict(row)
            for row in csv.DictReader(handle)
            if row["split"] == "test" and row["task"] in PHASE1_TASKS
        ]
    if not rows:
        raise ValueError("No phase-one test rows found")
    return rows


def _group_key(row: dict) -> str:
    """Return the narrowest reproducible group supported by the manifest."""
    dataset = row["dataset"]
    source_image = row["source_image"]
    leaf = Path(source_image).name
    if dataset == "13_zhanglab_oct":
        match = re.match(r"^[A-Za-z]+-(\d+)-", leaf)
        if not match:
            raise ValueError(f"Cannot extract ZhangLab patient ID: {source_image}")
        return f"13:{row['label']}:{match.group(1)}"
    if dataset == "03_eye_five_class":
        stem = Path(source_image).stem
        if stem.lower().startswith("aug_"):
            stem = stem[4:]
        return f"03:{row['label']}:{stem}"
    if dataset == "02_toxofundus":
        return f"02:{source_image}"
    if dataset == "01_uveitis_oct":
        return f"01:{row['source_group']}"
    return f"{dataset}:{row['source_group']}:{source_image}"


def _audit_train_test_groups(
    train_rows: list[dict],
    test_rows: list[dict],
) -> tuple[list[dict], dict]:
    """Exclude non-isolatable data and any train group seen in the test set."""
    test_keys_by_dataset: dict[str, set[str]] = defaultdict(set)
    for row in test_rows:
        test_keys_by_dataset[row["dataset"]].add(_group_key(row))

    eligible: list[dict] = []
    excluded: list[dict] = []
    for row in train_rows:
        reason = None
        if row["dataset"] == "01_uveitis_oct":
            reason = "no_patient_ids_and_all_source_groups_overlap_test"
        elif _group_key(row) in test_keys_by_dataset[row["dataset"]]:
            reason = "group_overlaps_test"
        if reason:
            excluded.append({**row, "exclusion_reason": reason})
        else:
            eligible.append(row)

    eligible_keys = {_group_key(row) for row in eligible}
    test_keys = set().union(*test_keys_by_dataset.values())
    overlap = sorted(eligible_keys & test_keys)
    if overlap:
        raise AssertionError(f"Eligible training groups overlap test: {overlap[:5]}")

    datasets: dict[str, dict] = {}
    for dataset in sorted({row["dataset"] for row in train_rows}):
        train_dataset_rows = [row for row in train_rows if row["dataset"] == dataset]
        eligible_dataset_rows = [row for row in eligible if row["dataset"] == dataset]
        excluded_dataset_rows = [
            row for row in excluded if row["dataset"] == dataset
        ]
        test_dataset_rows = [
            row for row in test_rows if row["dataset"] == dataset
        ]
        train_dataset_keys = {_group_key(row) for row in train_dataset_rows}
        test_dataset_keys = {
            _group_key(row) for row in test_dataset_rows
        }
        datasets[dataset] = {
            "train_rows": len(train_dataset_rows),
            "eligible_rows": len(eligible_dataset_rows),
            "excluded_rows": len(excluded_dataset_rows),
            "test_rows": len(test_dataset_rows),
            "train_groups": len(train_dataset_keys),
            "eligible_groups": len(
                {_group_key(row) for row in eligible_dataset_rows}
            ),
            "test_groups": len(test_dataset_keys),
            "shared_train_test_groups": len(
                train_dataset_keys & test_dataset_keys
            ),
        }

    exclusion_counts = Counter(
        f"{row['dataset']}::{row['exclusion_reason']}" for row in excluded
    )
    audit = {
        "policy": (
            "13=label+patient_id; 03=label+stem_with_aug_prefix_removed; "
            "02=image_path; 01=excluded"
        ),
        "datasets": datasets,
        "excluded_rows": len(excluded),
        "exclusion_counts": dict(sorted(exclusion_counts.items())),
        "eligible_rows": len(eligible),
        "eligible_groups": len(eligible_keys),
        "eligible_test_group_overlap": 0,
        "test_images_read": False,
    }
    return eligible, audit


def _split_validation(
    rows: list[dict],
    *,
    validation_groups_per_class: int,
    seed: int,
) -> tuple[list[dict], list[dict]]:
    """Hold out whole groups, stratified by task label."""
    buckets: dict[tuple[str, str], dict[str, list[dict]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in rows:
        buckets[(row["task"], row["label"])][_group_key(row)].append(row)
    rng = random.Random(seed + 1)
    train: list[dict] = []
    validation: list[dict] = []
    for key in sorted(buckets):
        groups = buckets[key]
        group_keys = sorted(groups)
        rng.shuffle(group_keys)
        count = min(
            validation_groups_per_class,
            len(group_keys) - 1,
        )
        if count < 1:
            raise ValueError(f"Not enough groups for validation class {key}")
        held_out = set(group_keys[:count])
        for group_key, group_rows in groups.items():
            target = validation if group_key in held_out else train
            target.extend(group_rows)
    train_keys = {_group_key(row) for row in train}
    validation_keys = {_group_key(row) for row in validation}
    overlap = train_keys & validation_keys
    if overlap:
        raise AssertionError(f"Train/validation group overlap: {sorted(overlap)[:5]}")
    rng.shuffle(train)
    rng.shuffle(validation)
    return train, validation


def _row_key(row: dict) -> str:
    return "\t".join(
        (
            row["task"],
            row["label"],
            row["source_group"],
            _group_key(row),
            row["image"],
        )
    )


def _rows_sha256(rows: list[dict]) -> str:
    payload = "\n".join(sorted(_row_key(row) for row in rows))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _class_balanced_schedule(
    rows: list[dict],
    *,
    steps: int,
    grad_accum: int,
    seed: int,
    task_weights: dict[str, int] | None = None,
) -> list[dict]:
    """Balance task labels while rotating across whole groups."""
    total = steps * grad_accum
    task_weights = task_weights or {task: 1 for task in PHASE1_TASKS}
    unknown_tasks = set(task_weights) - PHASE1_TASKS
    if unknown_tasks:
        raise ValueError(f"Unknown task weights: {sorted(unknown_tasks)}")
    if any(weight < 1 for weight in task_weights.values()):
        raise ValueError("Task weights must be positive integers")
    buckets: dict[tuple[str, str], dict[str, list[dict]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in rows:
        buckets[(row["task"], row["label"])][_group_key(row)].append(row)
    missing = [key for key in sorted(buckets) if not buckets[key]]
    if missing:
        raise ValueError(f"Empty class buckets: {missing}")

    rng = random.Random(seed + 2)
    keys = sorted(buckets)
    for key in keys:
        group_keys = sorted(buckets[key])
        rng.shuffle(group_keys)
        buckets[key] = defaultdict(
            list,
            {
                group_key: sorted(
                    buckets[key][group_key],
                    key=lambda row: row["image"],
                )
                for group_key in group_keys
            },
        )

    schedule: list[dict] = []
    cycle = 0
    while len(schedule) < total:
        cycle_rows: list[dict] = []
        for key in keys:
            groups = buckets[key]
            group_keys = list(groups)
            weight = task_weights.get(key[0], 1)
            for repeat in range(weight):
                ordinal = cycle * weight + repeat
                group_key = group_keys[ordinal % len(group_keys)]
                group_rows = groups[group_key]
                row_index = (ordinal // len(group_keys)) % len(group_rows)
                cycle_rows.append(group_rows[row_index])
        rng.shuffle(cycle_rows)
        schedule.extend(cycle_rows)
        cycle += 1
    return schedule[:total]


def _parse_task_weights(values: list[str]) -> dict[str, int]:
    weights = {task: 1 for task in PHASE1_TASKS}
    for value in values:
        task, separator, raw_weight = value.partition("=")
        if not separator or task not in PHASE1_TASKS:
            raise ValueError(
                f"Invalid --task-weight {value!r}; expected TASK=WEIGHT"
            )
        try:
            weight = int(raw_weight)
        except ValueError as exc:
            raise ValueError(f"Invalid task weight: {value!r}") from exc
        if not 1 <= weight <= 8:
            raise ValueError("Task weight must be between 1 and 8")
        weights[task] = weight
    return weights


def _selection_record(rows: list[dict]) -> list[dict]:
    return [
        {
            "dataset": row["dataset"],
            "task": row["task"],
            "label": row["label"],
            "source_group": row["source_group"],
            "group_key": _group_key(row),
            "image": row["image"],
        }
        for row in rows
    ]


def _write_jsonl(path: Path, value: object) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False) + "\n")


def _parse_label(text: str, task: str) -> str | None:
    match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    label = payload.get("label")
    from local_qwen4b_smoke import TASK_LABELS

    return label if label in TASK_LABELS[task] else None


def _classification_metrics(
    labels: list[str],
    predictions: list[str | None],
) -> dict:
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


def _validation_score(validation: dict) -> tuple[float, float, float]:
    return (
        float(validation["macro_f1"]),
        float(validation["json_valid_rate"]),
        -float(validation["loss"]),
    )


def _initialization_validation_score(validation: dict) -> tuple[float, float, float]:
    """Prefer macro-F1, then OCT F1, then lower loss for continuation."""
    oct_f1 = float(validation["per_task"]["oct_aux_4class"]["macro_f1"])
    return (
        float(validation["macro_f1"]),
        oct_f1,
        -float(validation["loss"]),
    )


def _validate(
    model,
    processor,
    rows: list[dict],
    *,
    torch,
    Image,
    image_pixels: int,
    max_length: int,
) -> dict:
    model.eval()
    losses: list[float] = []
    errors: list[str] = []
    outputs: list[dict] = []
    with torch.inference_mode():
        for row in rows:
            image = None
            try:
                with Image.open(_image_path(row)) as source:
                    image = source.convert("RGB")
                prompt, answer = _build_prompt(row["task"], row["label"])
                batch = _encode_example(
                    processor,
                    image,
                    prompt,
                    answer,
                    image_pixels=image_pixels,
                    max_length=max_length,
                )
                batch = {
                    key: value.to("cuda") if torch.is_tensor(value) else value
                    for key, value in batch.items()
                }
                output = model(**batch)
                losses.append(float(output.loss.detach().cpu()))
                del output, batch
                messages = [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image", "image": image},
                            {"type": "text", "text": prompt},
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
                    images=[image],
                    return_tensors="pt",
                    size={
                        "shortest_edge": image_pixels,
                        "longest_edge": image_pixels,
                    },
                )
                inputs = {
                    key: value.to("cuda") if torch.is_tensor(value) else value
                    for key, value in inputs.items()
                }
                generated = model.generate(
                    **inputs,
                    max_new_tokens=48,
                    do_sample=False,
                )
                generated = generated[:, inputs["input_ids"].shape[1] :]
                raw = processor.batch_decode(
                    generated,
                    skip_special_tokens=True,
                )[0]
                outputs.append(
                    {
                        "image": row["image"],
                        "task": row["task"],
                        "expected": row["label"],
                        "predicted": _parse_label(raw, row["task"]),
                        "raw": raw,
                    }
                )
                del inputs, generated
            except Exception as exc:
                errors.append(f"{row['image']}: {type(exc).__name__}: {exc}")
                outputs.append(
                    {
                        "image": row["image"],
                        "task": row["task"],
                        "expected": row["label"],
                        "predicted": None,
                        "raw": "",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
            finally:
                if image is not None:
                    image.close()
    model.train()
    if not outputs:
        raise RuntimeError("Validation produced no outputs")
    overall = _classification_metrics(
        [row["expected"] for row in outputs],
        [row["predicted"] for row in outputs],
    )
    per_task = {}
    for task in sorted({row["task"] for row in outputs}):
        task_outputs = [row for row in outputs if row["task"] == task]
        per_task[task] = _classification_metrics(
            [row["expected"] for row in task_outputs],
            [row["predicted"] for row in task_outputs],
        )
    return {
        "loss": sum(losses) / len(losses),
        "evaluated": len(losses),
        "errors": errors,
        "rows": len(rows),
        "accuracy": overall["accuracy"],
        "macro_f1": sum(
            metrics["macro_f1"] for metrics in per_task.values()
        ) / len(per_task),
        "json_valid_rate": overall["json_valid_rate"],
        "per_class": overall["per_class"],
        "confusion_matrix": overall["confusion_matrix"],
        "per_task": per_task,
        "outputs": outputs,
    }


def _save_checkpoint(
    model,
    optimizer,
    processor,
    run_dir: Path,
    *,
    step: int,
    best_loss: float,
    best_step: int,
    best_score: tuple[float, float, float],
    validation_metrics: dict | None,
    torch,
) -> Path:
    checkpoint_dir = run_dir / "checkpoints" / f"step-{step:06d}"
    checkpoint_dir.mkdir(parents=True, exist_ok=False)
    model.save_pretrained(checkpoint_dir)
    processor.save_pretrained(run_dir / "processor")
    torch.save(
        {
            "optimizer": optimizer.state_dict(),
            "step": step,
            "best_loss": best_loss,
            "best_step": best_step,
            "best_score": list(best_score),
        },
        checkpoint_dir / "training_state.pt",
    )
    _write_json(
        checkpoint_dir / "checkpoint.json",
        {
            "step": step,
            "validation_loss": (
                validation_metrics["loss"] if validation_metrics else None
            ),
            "validation_macro_f1": (
                validation_metrics["macro_f1"] if validation_metrics else None
            ),
            "validation_json_valid_rate": (
                validation_metrics["json_valid_rate"]
                if validation_metrics
                else None
            ),
            "best_loss": best_loss,
            "best_step": best_step,
            "best_score": list(best_score),
        },
    )
    _write_json(
        run_dir / "last_checkpoint.json",
        {
            "checkpoint_dir": str(checkpoint_dir.relative_to(ROOT)),
            "step": step,
        },
    )
    return checkpoint_dir


def _copy_adapter(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for name in ("adapter_config.json", "adapter_model.safetensors"):
        shutil.copy2(source / name, target / name)


def _restore_checkpoint(
    model,
    optimizer,
    run_dir: Path,
    *,
    torch,
) -> dict:
    last_path = run_dir / "last_checkpoint.json"
    if not last_path.is_file():
        return {
            "step": 0,
            "best_loss": math.inf,
            "best_step": 0,
            "best_score": (-math.inf, -math.inf, -math.inf),
        }
    last = json.loads(last_path.read_text(encoding="utf-8"))
    checkpoint_dir = ROOT / last["checkpoint_dir"]
    state_path = checkpoint_dir / "training_state.pt"
    adapter_path = checkpoint_dir / "adapter_model.safetensors"
    if not state_path.is_file() or not adapter_path.is_file():
        raise FileNotFoundError(f"Incomplete checkpoint: {checkpoint_dir}")
    from peft import set_peft_model_state_dict
    from safetensors.torch import load_file

    set_peft_model_state_dict(
        model,
        load_file(adapter_path),
        adapter_name="default",
    )
    state = torch.load(state_path, map_location="cpu", weights_only=False)
    optimizer.load_state_dict(state["optimizer"])
    return {
        "step": int(state["step"]),
        "best_loss": float(state.get("best_loss", math.inf)),
        "best_step": int(state.get("best_step", 0)),
        "best_score": tuple(
            state.get(
                "best_score",
                (-math.inf, -math.inf, -math.inf),
            )
        ),
    }


def _load_init_adapter(model, adapter_dir: Path) -> dict:
    from peft import PeftModel
    from safetensors.torch import load_file

    config_path = adapter_dir / "adapter_config.json"
    weights_path = adapter_dir / "adapter_model.safetensors"
    if not config_path.is_file() or not weights_path.is_file():
        raise FileNotFoundError(f"Incomplete initialization adapter: {adapter_dir}")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if int(config.get("r", -1)) != int(model.peft_config["default"].r):
        raise ValueError("Initialization adapter rank differs from --lora-r")
    from peft import set_peft_model_state_dict

    set_peft_model_state_dict(
        model,
        load_file(weights_path),
        adapter_name="default",
    )
    return {
        "directory": str(adapter_dir),
        "sha256": _sha256(weights_path),
        "rank": int(config["r"]),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="local-4060-grouped-cont-20261025-01")
    parser.add_argument("--steps", type=int, default=150)
    parser.add_argument("--grad-accum", type=int, default=4)
    parser.add_argument("--image-pixels", type=int, default=65_536)
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument("--learning-rate", type=float, default=2.5e-5)
    parser.add_argument("--lora-r", type=int, default=8)
    parser.add_argument("--validation-groups-per-class", type=int, default=3)
    parser.add_argument("--validation-every", type=int, default=25)
    parser.add_argument("--save-every", type=int, default=25)
    parser.add_argument("--early-stop-patience", type=int, default=3)
    parser.add_argument("--monitor-seconds", type=float, default=1.0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--init-adapter",
        type=Path,
        help="Adapter directory used to initialize a new run.",
    )
    parser.add_argument(
        "--task-weight",
        action="append",
        default=[],
        metavar="TASK=WEIGHT",
        help="Repeat a task this many times per schedule cycle (1-8).",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if not 1 <= args.steps <= 5000:
        raise ValueError("--steps must be between 1 and 5000")
    if not 1 <= args.grad_accum <= 32:
        raise ValueError("--grad-accum must be between 1 and 32")
    if not 4_096 <= args.image_pixels <= 451_584:
        raise ValueError("--image-pixels must be between 4096 and 451584")
    if not 128 <= args.max_length <= 1024:
        raise ValueError("--max-length must be between 128 and 1024")
    if not MODEL_DIR.is_dir() or not MANIFEST_PATH.is_file():
        raise FileNotFoundError("Local model or manifest is missing")
    task_weights = _parse_task_weights(args.task_weight)

    all_train = _load_phase1_train_rows()
    all_test = _load_phase1_test_rows()
    eligible_rows, split_audit = _audit_train_test_groups(all_train, all_test)
    train_rows, validation_rows = _split_validation(
        eligible_rows,
        validation_groups_per_class=args.validation_groups_per_class,
        seed=args.seed,
    )
    schedule = _class_balanced_schedule(
        train_rows,
        steps=args.steps,
        grad_accum=args.grad_accum,
        seed=args.seed,
        task_weights=task_weights,
    )
    class_counts = Counter(
        f"{row['task']}::{row['label']}" for row in schedule
    )
    split_record = {
        "steps": args.steps,
        "grad_accum": args.grad_accum,
        "train_rows": len(train_rows),
        "validation_rows": len(validation_rows),
        "train_groups": len({_group_key(row) for row in train_rows}),
        "validation_groups": len(
            {_group_key(row) for row in validation_rows}
        ),
        "validation_selection_sha256": _rows_sha256(validation_rows),
        "schedule_sha256": _rows_sha256(schedule),
        "schedule_exposures": len(schedule),
        "task_weights": task_weights,
        "class_exposures": dict(sorted(class_counts.items())),
        "validation_rows_detail": _selection_record(validation_rows),
        "test_intersection_audit": split_audit,
        "note": (
            "Whole groups are held out. 01 is excluded because it has no "
            "patient IDs and every source group overlaps test. 13 uses label "
            "plus patient ID to avoid splitting a label of the same patient "
            "while preserving multi-label patients. 03 is grouped "
            "by label and augmentation-stripped stem; 02 has no patient "
            "metadata, so each image remains its own group."
        ),
    }

    run_dir = ARTIFACTS_ROOT / args.run_id
    if args.dry_run:
        print(json.dumps(split_record, indent=2, ensure_ascii=False))
        return
    if run_dir.exists() and not args.resume:
        raise FileExistsError(f"Run directory already exists: {run_dir}")
    if args.init_adapter and args.resume:
        raise ValueError("--init-adapter and --resume are mutually exclusive")
    run_dir.mkdir(parents=True, exist_ok=True)
    if not (run_dir / "split.json").exists():
        _write_json(run_dir / "split.json", split_record)
    else:
        previous_split = json.loads(
            (run_dir / "split.json").read_text(encoding="utf-8")
        )
        if (
            previous_split["validation_selection_sha256"]
            != split_record["validation_selection_sha256"]
        ):
            raise ValueError(
                "Resume validation split differs from the saved run; "
                "use the original arguments or a new run id"
            )
        if previous_split["schedule_sha256"] != split_record["schedule_sha256"]:
            previous_exposures = int(previous_split["schedule_exposures"])
            if previous_exposures % args.grad_accum:
                raise ValueError(
                    "Previous schedule cannot be aligned to the current "
                    "gradient accumulation"
                )
            previous_steps = previous_exposures // args.grad_accum
            previous_schedule = _class_balanced_schedule(
                train_rows,
                steps=previous_steps,
                grad_accum=args.grad_accum,
                seed=args.seed,
                task_weights=task_weights,
            )
            if _rows_sha256(previous_schedule) != previous_split["schedule_sha256"]:
                raise ValueError(
                    "Previous schedule cannot be reproduced with the current "
                    "data, seed, or gradient accumulation"
                )
            if [
                _row_key(row) for row in previous_schedule
            ] != [
                _row_key(row) for row in schedule[:previous_exposures]
            ]:
                raise ValueError(
                    "Extended training schedule does not preserve the saved "
                    "schedule as an exact prefix"
                )
            split_record["schedule_history"] = [
                *previous_split.get("schedule_history", []),
                {
                    "steps": previous_split.get("steps", previous_steps),
                    "grad_accum": args.grad_accum,
                    "schedule_exposures": previous_exposures,
                    "schedule_sha256": previous_split["schedule_sha256"],
                },
            ]

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

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.cuda.manual_seed_all(args.seed)

    monitor = MemoryMonitor(
        run_dir / "memory_monitor.jsonl",
        torch,
        interval_seconds=args.monitor_seconds,
    )
    started_at = datetime.now(UTC)
    timer = time.perf_counter()
    status = "running"
    summary: dict = {
        "run_id": args.run_id,
        "status": status,
        "started_at": started_at.isoformat(),
        "mode": "local_stage1_grouped_generative_qlora",
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
            "target_steps": args.steps,
            "grad_accum": args.grad_accum,
            "learning_rate": args.learning_rate,
            "validation_every": args.validation_every,
            "save_every": args.save_every,
            "early_stop_patience": args.early_stop_patience,
            "seed": args.seed,
            "checkpoint_selection": "task_mean_macro_f1_then_json_rate_then_loss",
            "task_weights": task_weights,
            "init_adapter": (
                str(args.init_adapter.resolve()) if args.init_adapter else None
            ),
        },
        "split": {
            "train_rows": len(train_rows),
            "validation_rows": len(validation_rows),
            "train_groups": split_record["train_groups"],
            "validation_groups": split_record["validation_groups"],
            "validation_selection_sha256": split_record[
                "validation_selection_sha256"
            ],
            "schedule_sha256": split_record["schedule_sha256"],
            "class_exposures": split_record["class_exposures"],
            "test_intersection_audit": split_audit,
        },
    }

    model = None
    optimizer = None
    monitor.start()
    try:
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
        initialization = None
        if args.init_adapter:
            initialization = _load_init_adapter(
                model,
                args.init_adapter.resolve(),
            )
        optimizer = torch.optim.AdamW(
            trainable_parameters,
            lr=args.learning_rate,
        )
        restored = _restore_checkpoint(
            model,
            optimizer,
            run_dir,
            torch=torch,
        )
        for parameter_group in optimizer.param_groups:
            parameter_group["lr"] = args.learning_rate
        completed = restored["step"]
        best_loss = restored["best_loss"]
        best_step = restored["best_step"]
        best_score = restored["best_score"]
        if args.init_adapter and completed:
            raise ValueError("A fresh initialized run must not have a checkpoint")
        initialization_validation = None
        if args.init_adapter:
            initialization_started = time.perf_counter()
            initialization_validation = _validate(
                model,
                processor,
                validation_rows,
                torch=torch,
                Image=Image,
                image_pixels=args.image_pixels,
                max_length=args.max_length,
            )
            initialization_validation["step"] = 0
            initialization_validation["elapsed_seconds"] = (
                time.perf_counter() - initialization_started
            )
            best_loss = initialization_validation["loss"]
            best_score = _initialization_validation_score(
                initialization_validation
            )
            best_step = 0
            _write_jsonl(
                run_dir / "validation_metrics.jsonl",
                initialization_validation,
            )
            print(
                json.dumps(
                    {"event": "initialization_validation", **initialization_validation},
                    ensure_ascii=False,
                ),
                flush=True,
            )
            _write_json(
                run_dir / "best_checkpoint.json",
                {
                    "step": 0,
                    "initialization_adapter": initialization,
                    "validation_loss": initialization_validation["loss"],
                    "validation_macro_f1": initialization_validation[
                        "macro_f1"
                    ],
                    "validation_json_valid_rate": initialization_validation[
                        "json_valid_rate"
                    ],
                    "selection_score": list(best_score),
                    "adapter_sha256": initialization["sha256"],
                },
            )
            _copy_adapter(args.init_adapter.resolve(), run_dir / "best_adapter")
        summary["after_load"] = {
            "allocated_gib": torch.cuda.memory_allocated() / 1024**3,
            "reserved_gib": torch.cuda.memory_reserved() / 1024**3,
            "trainable_parameters": sum(
                parameter.numel() for parameter in trainable_parameters
            ),
            "resumed_from_step": completed,
            "initialization_adapter": initialization,
            "initialization_validation": (
                {
                    "loss": initialization_validation["loss"],
                    "accuracy": initialization_validation["accuracy"],
                    "macro_f1": initialization_validation["macro_f1"],
                    "oct_macro_f1": initialization_validation["per_task"][
                        "oct_aux_4class"
                    ]["macro_f1"],
                    "json_valid_rate": initialization_validation[
                        "json_valid_rate"
                    ],
                }
                if initialization_validation
                else None
            ),
        }
        print(
            json.dumps(
                {"event": "model_loaded", **summary["after_load"]},
                ensure_ascii=False,
            ),
            flush=True,
        )

        metrics_path = run_dir / "train_metrics.jsonl"
        validation_path = run_dir / "validation_metrics.jsonl"
        metrics_path.touch(exist_ok=True)
        validation_path.touch(exist_ok=True)
        start_index = completed * args.grad_accum
        stale_validations = 0
        truncated_reason = "target_steps"
        step_started = time.perf_counter()
        running_losses: list[float] = []
        last_gradient_norm = None

        for exposure_index in range(start_index, len(schedule)):
            row = schedule[exposure_index]
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
            loss = output.loss
            if not loss.requires_grad:
                raise RuntimeError("Training loss does not require gradients")
            loss_value = float(loss.detach().cpu())
            running_losses.append(loss_value)
            (loss / args.grad_accum).backward()
            del output, loss, batch

            if len(running_losses) < args.grad_accum:
                continue
            last_gradient_norm = torch.nn.utils.clip_grad_norm_(
                trainable_parameters,
                1.0,
            )
            optimizer.step()
            optimizer.zero_grad(set_to_none=True)
            completed += 1
            now = time.perf_counter()
            step_seconds = now - step_started
            step_started = now
            metric = {
                "time": datetime.now(UTC).isoformat(),
                "step": completed,
                "mean_loss": sum(running_losses) / len(running_losses),
                "gradient_norm": float(last_gradient_norm.detach().cpu()),
                "step_seconds": step_seconds,
                "samples": len(running_losses),
                "peak_allocated_gib": torch.cuda.max_memory_allocated()
                / 1024**3,
                "peak_reserved_gib": torch.cuda.max_memory_reserved() / 1024**3,
            }
            running_losses.clear()
            _write_jsonl(metrics_path, metric)
            print(json.dumps({"event": "train_step", **metric}), flush=True)

            should_validate = (
                completed % args.validation_every == 0
                or completed >= args.steps
            )
            validation = None
            if should_validate:
                validation_started = time.perf_counter()
                validation = _validate(
                    model,
                    processor,
                    validation_rows,
                    torch=torch,
                    Image=Image,
                    image_pixels=args.image_pixels,
                    max_length=args.max_length,
                )
                validation["step"] = completed
                validation["elapsed_seconds"] = (
                    time.perf_counter() - validation_started
                )
                _write_jsonl(validation_path, validation)
                print(
                    json.dumps(
                        {"event": "validation", **validation},
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
                validation_score = _validation_score(validation)
                if validation_score > best_score:
                    best_loss = validation["loss"]
                    best_step = completed
                    best_score = validation_score
                    stale_validations = 0
                    checkpoint_dir = _save_checkpoint(
                        model,
                        optimizer,
                        processor,
                        run_dir,
                        step=completed,
                        best_loss=best_loss,
                        best_step=best_step,
                        best_score=best_score,
                        validation_metrics=validation,
                        torch=torch,
                    )
                    _copy_adapter(checkpoint_dir, run_dir / "best_adapter")
                    _write_json(
                        run_dir / "best_checkpoint.json",
                        {
                            "step": completed,
                            "validation_loss": validation["loss"],
                            "validation_macro_f1": validation["macro_f1"],
                            "validation_json_valid_rate": validation[
                                "json_valid_rate"
                            ],
                            "selection_score": list(best_score),
                            "checkpoint_dir": str(checkpoint_dir.relative_to(ROOT)),
                            "adapter_sha256": _sha256(
                                checkpoint_dir / "adapter_model.safetensors"
                            ),
                        },
                    )
                else:
                    stale_validations += 1
                    checkpoint_dir = _save_checkpoint(
                        model,
                        optimizer,
                        processor,
                        run_dir,
                        step=completed,
                        best_loss=best_loss,
                        best_step=best_step,
                        best_score=best_score,
                        validation_metrics=validation,
                        torch=torch,
                    )
                if stale_validations >= args.early_stop_patience:
                    truncated_reason = "early_stopping"
                    break
            elif args.save_every and completed % args.save_every == 0:
                _save_checkpoint(
                    model,
                    optimizer,
                    processor,
                    run_dir,
                    step=completed,
                    best_loss=best_loss,
                    best_step=best_step,
                    best_score=best_score,
                    validation_metrics=None,
                    torch=torch,
                )
            if completed >= args.steps:
                truncated_reason = "target_steps"
                break

        final_adapter = run_dir / "final_adapter"
        model.save_pretrained(final_adapter)
        processor.save_pretrained(run_dir / "processor")
        if not (run_dir / "best_adapter" / "adapter_model.safetensors").is_file():
            _copy_adapter(final_adapter, run_dir / "best_adapter")
            best_step = completed
            best_loss = float("nan")
            best_score = (-math.inf, -math.inf, -math.inf)
        status = "ok"
        summary.update(
            {
                "status": status,
                "completed_steps": completed,
                "truncated_reason": truncated_reason,
                "best_step": best_step,
                "best_validation_loss": best_loss,
                "best_validation_macro_f1": best_score[0],
                "best_validation_json_valid_rate": best_score[1],
                "selection_score": list(best_score),
                "last_gradient_norm": (
                    float(last_gradient_norm.detach().cpu())
                    if last_gradient_norm is not None
                    else None
                ),
                "final_adapter": {
                    "directory": str(final_adapter.relative_to(ROOT)),
                    "sha256": _sha256(
                        final_adapter / "adapter_model.safetensors"
                    ),
                },
                "best_adapter": {
                    "directory": str((run_dir / "best_adapter").relative_to(ROOT)),
                    "sha256": _sha256(
                        run_dir / "best_adapter" / "adapter_model.safetensors"
                    ),
                },
                "peak_allocated_gib": torch.cuda.max_memory_allocated()
                / 1024**3,
                "peak_reserved_gib": torch.cuda.max_memory_reserved()
                / 1024**3,
            }
        )
    except Exception as exc:
        status = "failed"
        summary.update(
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
            summary["final_memory"] = {
                "allocated_gib": torch.cuda.memory_allocated() / 1024**3,
                "reserved_gib": torch.cuda.memory_reserved() / 1024**3,
                "peak_allocated_gib": torch.cuda.max_memory_allocated()
                / 1024**3,
                "peak_reserved_gib": torch.cuda.max_memory_reserved() / 1024**3,
            }
        summary["total_seconds"] = time.perf_counter() - timer
        summary["finished_at"] = datetime.now(UTC).isoformat()
        if status == "ok":
            current_history = split_record.get("schedule_history", [])
            if not current_history or (
                current_history[-1]["schedule_sha256"]
                != split_record["schedule_sha256"]
            ):
                current_history.append(
                    {
                        "steps": args.steps,
                        "grad_accum": args.grad_accum,
                        "schedule_exposures": len(schedule),
                        "schedule_sha256": split_record["schedule_sha256"],
                    }
                )
            split_record["schedule_history"] = current_history
            _write_json(run_dir / "split.json", split_record)
        _write_json(run_dir / "training_summary.json", summary)
        print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)
        del model, optimizer
        if torch.cuda.is_initialized():
            torch.cuda.empty_cache()


if __name__ == "__main__":
    main()

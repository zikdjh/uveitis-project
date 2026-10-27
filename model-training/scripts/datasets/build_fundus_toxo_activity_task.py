"""Build the 3-class ocular toxoplasmosis activity task from unused rows.

``02_toxofundus`` ships doctor-assigned activity labels (``healthy`` /
``active`` / ``inactive`` plus multi-lesion combinations) for 412 images, but
the staged binary task already froze its 82-row test split:

* ``fundus_toxo_binary`` test = 82 rows, evaluated once by
  ``toxo-test-20261027-01`` (macro-F1 0.907345).

That split is consumed and must never be reused, so this builder only reads the
330 ``train`` rows of the binary task and carves a *fresh* internal development
holdout out of them. The consumed 82 rows are excluded entirely and their
pixels are never opened.

The label mapping is inclusive on active disease because the release defines
``active/inactive`` as "active and old lesions both present": any raw label that
mentions an active lesion becomes ``active``.

Output is a task-local ``manifest.csv`` + ``audit.json``. The holdout is an
internal development split only; it is an image-level split with no patient
identifiers and must not be reported as external or patient-isolated
validation.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SOURCE_ROOT = (
    PROJECT_ROOT / "model-training" / "datasets" / "extracted" / "02_toxofundus"
)
LABELS_CSV = SOURCE_ROOT / "dataset_labels.csv"
TRAINING_MANIFEST = (
    PROJECT_ROOT / "model-training" / "datasets" / "training" / "manifest.csv"
)
OUTPUT = (
    PROJECT_ROOT
    / "model-training"
    / "datasets"
    / "tasks"
    / "fundus_toxo_activity_3class"
)

DATASET = "02_toxofundus"
SOURCE_TASK = "fundus_toxo_binary"
TASK = "fundus_toxo_activity_3class"
LABELS = ["active", "healthy", "inactive"]

# The published label sheet lists ``2809.jpg`` while the image archive ships
# ``2805.jpg``; it is the only mismatch on either side.
RECONCILE = {"2805.jpg": "2809.jpg"}

CONSUMED_TEST_RUN = "toxo-test-20261027-01"
DEFAULT_DEV_FRACTION = 0.20
DEFAULT_SEED = 20261027


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--dev-fraction", type=float, default=DEFAULT_DEV_FRACTION)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    return parser.parse_args()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_raw_labels() -> dict[str, str]:
    with LABELS_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    labels: dict[str, str] = {}
    for row in rows:
        name = (row.get("Image name") or "").strip()
        label = (row.get("Label") or "").strip()
        if not name or not label:
            raise ValueError(f"Incomplete label row: {row}")
        if name in labels:
            raise ValueError(f"Duplicate label entry: {name}")
        labels[name] = label
    if len(labels) != 412:
        raise ValueError(f"Expected 412 label rows, got {len(labels)}")
    return labels


def _to_activity(raw_label: str) -> str:
    """Map a raw release label to the inclusive 3-class activity label."""
    tokens = {token.strip().lower() for token in raw_label.split("/") if token.strip()}
    if tokens == {"healthy"}:
        return "healthy"
    if "active" in tokens:
        return "active"
    if tokens == {"inactive"}:
        return "inactive"
    raise ValueError(f"Unmapped raw label: {raw_label!r}")


def main() -> int:
    args = _parse_args()
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    if not 0.05 <= args.dev_fraction <= 0.4:
        raise ValueError("--dev-fraction must be between 0.05 and 0.4")

    raw_labels = _load_raw_labels()
    if sum(1 for name in raw_labels) != 412:
        raise ValueError("Unexpected label sheet size")

    with TRAINING_MANIFEST.open("r", encoding="utf-8", newline="") as handle:
        staged = [
            dict(row)
            for row in csv.DictReader(handle)
            if row["dataset"] == DATASET and row["task"] == SOURCE_TASK
        ]
    binary_train = [row for row in staged if row["split"] == "train"]
    binary_test = [row for row in staged if row["split"] == "test"]
    if len(binary_train) != 330 or len(binary_test) != 82:
        raise ValueError(
            "Unexpected binary split sizes: "
            f"train={len(binary_train)} test={len(binary_test)}"
        )
    consumed_test_images = {Path(row["source_image"]).name for row in binary_test}

    raw_counts: Counter[str] = Counter()
    mapped_counts: Counter[str] = Counter()
    records: list[dict] = []
    reconciled: dict[str, str] = {}
    for row in binary_train:
        image_name = Path(row["source_image"]).name
        if image_name in consumed_test_images:
            raise AssertionError(
                f"Source row unexpectedly belongs to the consumed test set: {image_name}"
            )
        label_name = RECONCILE.get(image_name, image_name)
        if image_name in RECONCILE:
            reconciled[image_name] = label_name
        if label_name not in raw_labels:
            raise ValueError(f"No source label for {image_name}")
        raw_label = raw_labels[label_name]
        activity = _to_activity(raw_label)
        raw_counts[raw_label] += 1
        mapped_counts[activity] += 1
        records.append(
            {
                **row,
                "task": TASK,
                "label": activity,
                "_raw_label": raw_label,
                "_image_name": image_name,
            }
        )

    if len(records) != 330:
        raise ValueError(f"Expected 330 candidate rows, got {len(records)}")
    if set(mapped_counts) != set(LABELS):
        raise ValueError(f"Missing classes after mapping: {sorted(mapped_counts)}")

    # Deterministic, class-stratified internal development holdout.
    rng = random.Random(args.seed)
    by_class: dict[str, list[dict]] = {label: [] for label in LABELS}
    for record in records:
        by_class[record["label"]].append(record)
    dev_rows: list[dict] = []
    train_rows: list[dict] = []
    for label in LABELS:
        bucket = sorted(by_class[label], key=lambda item: item["_image_name"])
        rng.shuffle(bucket)
        holdout = max(1, int(round(len(bucket) * args.dev_fraction)))
        dev_rows.extend(bucket[:holdout])
        train_rows.extend(bucket[holdout:])

    for record in train_rows:
        record["split"] = "train"
    for record in dev_rows:
        record["split"] = "test"

    train_images = {record["_image_name"] for record in train_rows}
    dev_images = {record["_image_name"] for record in dev_rows}
    if train_images & dev_images:
        raise AssertionError("Internal train/dev image overlap")
    if (train_images | dev_images) & consumed_test_images:
        raise AssertionError("Raw rows collide with the consumed test set")

    fields = list(staged[0].keys())
    ordered = train_rows + dev_rows
    for record in ordered:
        extras = set(record) - set(fields)
        if extras != {"_raw_label", "_image_name"}:
            raise ValueError(f"Unexpected extra fields: {sorted(extras)}")

    manifest_rows = [{key: record[key] for key in fields} for record in ordered]
    for record, manifest_row in zip(ordered, manifest_rows, strict=True):
        if list(manifest_row) != fields:
            raise ValueError("Row field order differs from the header")

    output.mkdir(parents=True)
    manifest_path = output / "manifest.csv"
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(manifest_rows)

    audit = {
        "status": "ok",
        "task": TASK,
        "task_dir": "model-training/datasets/tasks/fundus_toxo_activity_3class",
        "source": "model-training/datasets/extracted/02_toxofundus",
        "source_task": SOURCE_TASK,
        "license": "CC BY 4.0",
        "license_scope": "research and commercial use with attribution",
        "labels": LABELS,
        "label_mapping": "inclusive_active",
        "rows": len(manifest_rows),
        "split_counts": dict(sorted(Counter(r["split"] for r in manifest_rows).items())),
        "label_split_counts": dict(
            sorted(Counter(f"{r['split']}::{r['label']}" for r in manifest_rows).items())
        ),
        "label_counts": dict(sorted(mapped_counts.items())),
        "raw_label_counts": dict(sorted(raw_counts.items())),
        "source_rows_available": len(staged),
        "consumed_test_rows_excluded": len(binary_test),
        "consumed_test_run": CONSUMED_TEST_RUN,
        "consumed_test_images_read": False,
        "patient_id_available": False,
        "patient_isolated_split": False,
        "doctor_annotation_evidence": True,
        "external_validation_claim": "prohibited_consumed_test",
        "validation_scope": "internal_development_only",
        "filename_reconciliation": reconciled,
        "internal_train_dev_image_overlap": 0,
        "dev_fraction": args.dev_fraction,
        "split_seed": args.seed,
        "source_labels_sha256": _sha256(LABELS_CSV),
        "source_manifest_sha256": _sha256(TRAINING_MANIFEST),
        "manifest_sha256": _sha256(manifest_path),
        "note": (
            "Built only from the 330 binary-task train rows; the 82-row binary "
            "test split is consumed by toxo-test-20261027-01 and is excluded. "
            "ToxoFundus has no patient identifiers, so the internal holdout is "
            "an image-level development split and cannot be reported as "
            "external or patient-isolated validation."
        ),
    }
    (output / "audit.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(audit, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

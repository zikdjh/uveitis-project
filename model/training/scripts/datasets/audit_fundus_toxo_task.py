"""Audit the fundus_toxo_binary task without rebuilding its manifest.

The ocular toxoplasmosis task (source ``02_toxofundus``) already ships in the
staged training manifest ``model/training/datasets/training/manifest.csv``.
This script instead verifies the chain source labels -> staged images ->
training manifest, records the single filename reconciliation
(``2809.jpg`` in the label sheet vs ``2805.jpg`` on disk), and writes a
task-level audit next to the other task folders.

It does not modify any existing manifest or image, and it never reads the
frozen OCT test split.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SOURCE_ROOT = (
    PROJECT_ROOT / "model/training" / "datasets" / "extracted" / "02_toxofundus"
)
LABELS_CSV = SOURCE_ROOT / "dataset_labels.csv"
SOURCE_IMAGES = SOURCE_ROOT / "images"
SOURCE_MASKS = SOURCE_ROOT / "masks"
STAGED_IMAGES = (
    PROJECT_ROOT
    / "model/training"
    / "datasets"
    / "training"
    / "data"
    / "02_toxofundus"
    / "02_toxofundus"
    / "images"
)
TRAINING_MANIFEST = (
    PROJECT_ROOT / "model/training" / "datasets" / "training" / "manifest.csv"
)
OUTPUT = (
    PROJECT_ROOT
    / "model/training"
    / "datasets"
    / "tasks"
    / "fundus_toxo_binary"
    / "audit.json"
)

DATASET = "02_toxofundus"
TASK = "fundus_toxo_binary"
# The published release lists ``2809.jpg`` in the label sheet while the image
# archive ships ``2805.jpg``. It is the only mismatch on either side, so the
# pair is reconciled explicitly and never matched silently.
RECONCILE = {"2809.jpg": "2805.jpg"}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT,
        help="Audit JSON destination (defaults to the fundus_toxo_binary task).",
    )
    return parser.parse_args()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _to_binary(raw_label: str) -> str:
    return "healthy" if raw_label.strip().lower() == "healthy" else "toxoplasmosis"


def _load_labels() -> dict[str, str]:
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


def main() -> int:
    args = _parse_args()
    output = args.output.resolve()

    labels = _load_labels()
    source_images = {path.name: path for path in SOURCE_IMAGES.glob("*") if path.is_file()}
    if len(source_images) != 412:
        raise ValueError(f"Expected 412 source images, got {len(source_images)}")

    unmatched_labels = sorted(set(labels) - set(source_images))
    unmatched_images = sorted(set(source_images) - set(labels))
    if unmatched_labels != ["2809.jpg"] or unmatched_images != ["2805.jpg"]:
        raise ValueError(
            "Unexpected filename mismatch; auditing assumptions changed: "
            f"labels_only={unmatched_labels}, images_only={unmatched_images}"
        )

    staged = {
        path.name: path for path in STAGED_IMAGES.glob("*") if path.is_file()
    }
    if set(staged) != set(source_images):
        raise ValueError("Staged images do not match the extracted source set")

    with TRAINING_MANIFEST.open("r", encoding="utf-8", newline="") as handle:
        manifest_rows = [
            dict(row)
            for row in csv.DictReader(handle)
            if row["dataset"] == DATASET
        ]
    if not manifest_rows:
        raise ValueError("No fundus_toxo_binary rows in the training manifest")

    reconciled: dict[str, str] = {}
    split_counts: Counter[str] = Counter()
    label_split_counts: Counter[str] = Counter()
    raw_label_counts: Counter[str] = Counter()
    image_hashes: dict[str, str] = {}
    duplicate_content: list[list[str]] = []
    seen_images: set[str] = set()

    for row in manifest_rows:
        image_name = Path(row["source_image"]).name
        if image_name in seen_images:
            raise ValueError(f"Duplicate manifest image: {image_name}")
        seen_images.add(image_name)

        label_name = image_name
        if image_name in RECONCILE.values():
            label_name = next(k for k, v in RECONCILE.items() if v == image_name)
            reconciled[image_name] = label_name
        if label_name not in labels:
            raise ValueError(f"No source label for {image_name}")

        raw_label = labels[label_name]
        expected = _to_binary(raw_label)
        if row["label"] != expected:
            raise ValueError(
                f"Label mismatch for {image_name}: manifest={row['label']} "
                f"expected={expected} (raw={raw_label})"
            )
        if row["task"] != TASK:
            raise ValueError(f"Unexpected task for {image_name}: {row['task']}")

        digest = _sha256(source_images[image_name])
        if digest in image_hashes:
            duplicate_content.append([image_hashes[digest], image_name])
        image_hashes[digest] = image_name

        raw_label_counts[raw_label] += 1
        split_counts[row["split"]] += 1
        label_split_counts[f"{row['split']}::{row['label']}"] += 1

    if set(seen_images) != set(source_images):
        missing = sorted(set(source_images) - seen_images)
        raise ValueError(f"Manifest is missing {len(missing)} images; first={missing[:3]}")
    if len(reconciled) != 1:
        raise ValueError(f"Expected exactly one reconciled filename, got {reconciled}")

    mask_stems = {path.stem for path in SOURCE_MASKS.glob("*") if path.is_file()}
    image_stems = {Path(name).stem for name in source_images}
    masks_matched = len(image_stems & mask_stems)

    audit = {
        "status": "ok",
        "task": TASK,
        "source": "model/training/datasets/extracted/02_toxofundus",
        "manifest": "model/training/datasets/training/manifest.csv",
        "license": "CC BY 4.0",
        "license_scope": "research and commercial use with attribution",
        "labels": ["healthy", "toxoplasmosis"],
        "images": len(manifest_rows),
        "masks": len([p for p in SOURCE_MASKS.glob("*") if p.is_file()]),
        "images_with_matching_mask": masks_matched,
        "raw_label_counts": dict(sorted(raw_label_counts.items())),
        "split_counts": dict(sorted(split_counts.items())),
        "label_split_counts": dict(sorted(label_split_counts.items())),
        "patient_id_available": False,
        "patient_isolated_split": False,
        "doctor_annotation_evidence": True,
        "external_validation_claim": "prohibited",
        "filename_reconciliation": reconciled,
        "duplicate_image_content": len(duplicate_content),
        "duplicate_content_examples": duplicate_content[:5],
        "source_labels_sha256": _sha256(LABELS_CSV),
        "training_manifest_sha256": _sha256(TRAINING_MANIFEST),
        "frozen_oct_test_images_read": False,
        "note": (
            "ToxoFundus has no patient identifiers, so the existing train/test "
            "split is an image-level split and cannot be reported as "
            "patient-isolated external validation. Labels were assigned by "
            "ophthalmologists, but the task is ocular toxoplasmosis, a single "
            "infectious uveitis subtype, not general uveitis."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(audit, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

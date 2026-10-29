"""Derive Open UWF 700 uveitis-vs-control task from the audited 7-class task.

The source 7-class task selected whole diagnosis-scoped patient groups into
train, validation, and test. This script keeps those immutable assignments and
only collapses labels to ``uveitis`` or ``non_uveitis``. No image is copied or
read; the manifest continues to reference the extracted source images.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SOURCE = (
    PROJECT_ROOT
    / "training"
    / "datasets"
    / "tasks"
    / "open_uwf_7class"
    / "manifest.csv"
)
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "training"
    / "datasets"
    / "tasks"
    / "open_uwf_uveitis_binary"
)
TASK = "uwf_uveitis_binary"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"Task directory already exists: {output}")
    if not source.is_file():
        raise FileNotFoundError(source)

    with source.open("r", encoding="utf-8", newline="") as handle:
        source_rows = list(csv.DictReader(handle))
    if len(source_rows) != 700:
        raise ValueError(f"Expected 700 source rows, got {len(source_rows)}")

    output_rows: list[dict[str, str]] = []
    for row in source_rows:
        label = "uveitis" if row["label"] == "Uveitis" else "non_uveitis"
        source_image = row["source_image"]
        if not source_image.startswith("Original UWF Image/"):
            raise ValueError(f"Unexpected Open UWF source path: {source_image}")
        output_rows.append(
            {
                "dataset": row["dataset"],
                "task": TASK,
                "label": label,
                "source_group": row["source_group"],
                "source_split": "",
                "split": row["split"],
                "image": row["image"],
                "source_image": source_image,
            }
        )

    group_splits: dict[str, set[str]] = defaultdict(set)
    for row in output_rows:
        group_splits[row["source_group"]].add(row["split"])
    leaking = sorted(
        group for group, splits in group_splits.items() if len(splits) > 1
    )
    if leaking:
        raise AssertionError(f"Patient groups cross splits: {leaking[:5]}")

    split_counts = Counter(row["split"] for row in output_rows)
    label_split_counts = Counter(
        f"{row['split']}::{row['label']}" for row in output_rows
    )
    for split in ("train", "validation", "test"):
        for label in ("non_uveitis", "uveitis"):
            if label_split_counts[f"{split}::{label}"] < 1:
                raise ValueError(f"Empty {split} class: {label}")

    output.mkdir(parents=True)
    manifest = output / "manifest.csv"
    fields = list(output_rows[0])
    with manifest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output_rows)

    audit = {
        "status": "ok",
        "task": TASK,
        "source_manifest": str(source.relative_to(PROJECT_ROOT)),
        "images": len(output_rows),
        "labels": ["non_uveitis", "uveitis"],
        "split_counts": dict(sorted(split_counts.items())),
        "label_split_counts": dict(sorted(label_split_counts.items())),
        "patient_groups": len(group_splits),
        "source_patient_group_assignments_changed": False,
        "cross_split_patient_groups": 0,
        "images_copied": False,
        "images_read": False,
        "frozen_test_images_read": False,
        "note": (
            "Non-uveitis includes AMD, DR, healthy, pathologic myopia, "
            "retinal detachment, and RVO. This is a research proxy task, "
            "not clinical exclusion of all non-uveitic inflammatory disease."
        ),
    }
    (output / "audit.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(audit, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Build the patient-isolated Open UWF 700 task from source XLSX metadata.

The source does not expose a single image directory containing a direct label
column. Labels are derived from the image path, while patient identity comes
from ``Demographics of the participants.xlsx``. Patient IDs are reused across
diagnosis cohorts, so the reproducible group key includes the diagnosis.

The script copies only images and writes a task-local manifest and audit. It
does not modify the extracted source dataset or the existing multi-task
training staging tree.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SOURCE_ROOT = (
    PROJECT_ROOT
    / "model-training"
    / "datasets"
    / "extracted"
    / "14_open_uwf700"
)
IMAGE_ROOT = SOURCE_ROOT / "Original UWF Image"
DEMOGRAPHICS_PATH = SOURCE_ROOT / "Demographics of the participants.xlsx"
LABELS = ("AMD", "DR", "Healthy", "PM", "RD", "RVO", "Uveitis")
TASK = "uwf_7class"
SPREADSHEET_NAMESPACE = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT
        / "model-training"
        / "datasets"
        / "tasks"
        / "open_uwf_7class",
    )
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help="Write manifest and audit without copying image files.",
    )
    return parser.parse_args()


def _read_xlsx_rows(path: Path) -> list[list[str]]:
    """Read the first worksheet without pandas or openpyxl."""
    with zipfile.ZipFile(path) as archive:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall("m:si", SPREADSHEET_NAMESPACE):
                shared_strings.append(
                    "".join(
                        node.text or ""
                        for node in item.findall(".//m:t", SPREADSHEET_NAMESPACE)
                    )
                )

        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        rows: list[list[str]] = []
        for row in sheet.findall(".//m:row", SPREADSHEET_NAMESPACE):
            values: list[str] = []
            for cell in row.findall("m:c", SPREADSHEET_NAMESPACE):
                value_node = cell.find("m:v", SPREADSHEET_NAMESPACE)
                inline_node = cell.find("m:is/m:t", SPREADSHEET_NAMESPACE)
                if cell.get("t") == "s" and value_node is not None:
                    values.append(shared_strings[int(value_node.text or "")])
                elif inline_node is not None:
                    values.append(inline_node.text or "")
                else:
                    values.append(value_node.text or "" if value_node is not None else "")
            rows.append(values)
    return rows


def _load_metadata() -> dict[str, dict[str, str]]:
    rows = _read_xlsx_rows(DEMOGRAPHICS_PATH)
    if not rows:
        raise ValueError("Demographics worksheet is empty")
    headers = [value.strip() for value in rows[0]]
    required = {"Image ID", "Patient ID", "Eye ID", "Eye category", "Diagnosis"}
    missing = sorted(required - set(headers))
    if missing:
        raise ValueError(f"Demographics worksheet is missing columns: {missing}")

    metadata: dict[str, dict[str, str]] = {}
    for raw in rows[1:]:
        values = [*raw, *("" for _ in range(len(headers) - len(raw)))]
        record = {
            key: value.strip()
            for key, value in zip(headers, values, strict=False)
        }
        image_name = record["Image ID"]
        if not image_name or not record["Patient ID"] or not record["Diagnosis"]:
            raise ValueError(f"Incomplete demographics row: {record}")
        if image_name in metadata:
            raise ValueError(f"Duplicate Image ID: {image_name}")
        metadata[image_name] = record
    if len(metadata) != 700:
        raise ValueError(f"Expected 700 demographics rows, got {len(metadata)}")
    return metadata


def _stable_split(patient_group: str) -> str:
    rank = int(hashlib.sha256(patient_group.encode("utf-8")).hexdigest(), 16)
    bucket = rank % 100
    if bucket < 70:
        return "train"
    if bucket < 85:
        return "validation"
    return "test"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    args = _parse_args()
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"Task directory already exists: {output}")

    metadata = _load_metadata()
    image_paths = {
        path.name: path
        for path in IMAGE_ROOT.rglob("*.jpg")
        if path.is_file()
    }
    if set(image_paths) != set(metadata):
        missing_images = sorted(set(metadata) - set(image_paths))
        missing_metadata = sorted(set(image_paths) - set(metadata))
        raise ValueError(
            f"Image/metadata mismatch: missing_images={missing_images[:5]}, "
            f"missing_metadata={missing_metadata[:5]}"
        )

    records: list[dict[str, str]] = []
    image_hashes: dict[str, str] = {}
    for image_name, record in sorted(metadata.items()):
        source = image_paths[image_name]
        label = record["Diagnosis"]
        if label not in LABELS:
            raise ValueError(f"Unexpected UWF label {label!r} for {image_name}")
        if source.parent.name != label:
            raise ValueError(
                f"Label/source directory mismatch for {image_name}: "
                f"{label} != {source.parent.name}"
            )
        patient_group = f"14_open_uwf700:{label}:{record['Patient ID']}"
        digest = _sha256(source)
        if digest in image_hashes:
            raise ValueError(
                f"Duplicate image content: {image_name} and {image_hashes[digest]}"
            )
        image_hashes[digest] = image_name
        records.append(
            {
                "dataset": "14_open_uwf700",
                "task": TASK,
                "label": label,
                "source_group": patient_group,
                "source_split": "",
                "split": _stable_split(patient_group),
                "image": f"data/{image_name}",
                "source_image": source.relative_to(SOURCE_ROOT).as_posix(),
                "patient_id": record["Patient ID"],
                "eye_id": record["Eye ID"],
                "eye_category": record["Eye category"],
            }
        )

    group_splits: dict[str, set[str]] = defaultdict(set)
    for record in records:
        group_splits[record["source_group"]].add(record["split"])
    leaking_groups = sorted(
        group for group, splits in group_splits.items() if len(splits) > 1
    )
    if leaking_groups:
        raise AssertionError(f"Patient groups cross splits: {leaking_groups[:5]}")

    split_counts = Counter(record["split"] for record in records)
    label_split_counts = Counter(
        f"{record['split']}::{record['label']}" for record in records
    )
    for split in ("train", "validation", "test"):
        for label in LABELS:
            if label_split_counts[f"{split}::{label}"] < 1:
                raise ValueError(f"Empty {split} class: {label}")

    output.mkdir(parents=True)
    if not args.metadata_only:
        data_dir = output / "data"
        data_dir.mkdir()
        for record in records:
            source = IMAGE_ROOT / record["image"].removeprefix("data/")
            destination = output / record["image"]
            shutil.copy2(source, destination)

    manifest_path = output / "manifest.csv"
    fields = list(records[0])
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)

    audit = {
        "status": "ok",
        "task": TASK,
        "source": str(SOURCE_ROOT.relative_to(PROJECT_ROOT)),
        "license": "CC BY 4.0",
        "license_scope": "research and commercial use with attribution",
        "images": len(records),
        "files_materialized": not args.metadata_only,
        "bytes": (
            0
            if args.metadata_only
            else sum((output / row["image"]).stat().st_size for row in records)
        ),
        "split_counts": dict(sorted(split_counts.items())),
        "label_split_counts": dict(sorted(label_split_counts.items())),
        "patient_groups": len(group_splits),
        "group_key_policy": "14_open_uwf700:<diagnosis>:<Patient ID>",
        "patient_ids_reused_across_cohorts": True,
        "cross_split_patient_groups": 0,
        "duplicate_image_content": 0,
        "manifest_sha256": _sha256(manifest_path),
        "source_xlsx_sha256": _sha256(DEMOGRAPHICS_PATH),
        "source_images_read": True,
        "frozen_oct_test_images_read": False,
        "note": (
            "The source Patient ID is not global across diagnosis cohorts. "
            "Include diagnosis in the patient group key. Splits were selected "
            "by stable hash of the full patient group, never by image."
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

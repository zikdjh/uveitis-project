"""Build the deterministic image subset used by the Modal $44 training plan.

Run from the repository root with a Python interpreter that has only the
standard library available:

    python model/training/scripts/modal/build_budget_training_subset.py

The script copies images into a local staging tree; it never modifies source
datasets.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
UV_DATASETS = ("01_uveitis_oct", "02_toxofundus", "03_eye_five_class")
OCT_AUX_NAME = "13_zhanglab_oct"
UWF_NAME = "14_open_uwf700"
RFMID_SPLITS = ("Training_set", "Validation_set", "Test_set")
UWF_LABELS = ("AMD", "DR", "Healthy", "PM", "RD", "RVO", "Uveitis")
XLSX_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


@dataclass(frozen=True)
class ImageRecord:
    dataset: str
    task: str
    label: str
    source_group: str
    source_split: str
    split: str
    source: Path
    relative_path: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("model/training/datasets/extracted"),
        help="Extracted dataset root.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("model/training/datasets/training"),
        help="Local training staging directory to upload.",
    )
    parser.add_argument(
        "--odir-train",
        type=int,
        default=2_000,
        help="ODIR training images; left and right eyes share a patient.",
    )
    parser.add_argument(
        "--zhang-per-class",
        type=int,
        default=2_500,
        help="ZhangLab OCT train images per class.",
    )
    return parser.parse_args()


def image_files(root: Path) -> list[Path]:
    return sorted(
        (
            path
            for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
        ),
        key=lambda path: path.as_posix(),
    )


def stable_rank(value: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{value}".encode("utf-8")).hexdigest()


def split_uv_files(
    files: list[Path], holdout_fraction: float, salt: str
) -> tuple[list[Path], list[Path]]:
    ranked = sorted(files, key=lambda path: stable_rank(path.as_posix(), salt))
    holdout_count = max(1, round(len(ranked) * holdout_fraction))
    return ranked[holdout_count:], ranked[:holdout_count]


def add_class_split(
    records: list[ImageRecord],
    *,
    source: Path,
    dataset: str,
    task: str,
    files: list[Path],
    label: str,
    source_group: str,
    holdout_fraction: float = 0.2,
) -> None:
    train_files, test_files = split_uv_files(
        files, holdout_fraction, f"{dataset}:{task}:{label}"
    )
    for split, selected in (("train", train_files), ("test", test_files)):
        for path in selected:
            records.append(
                ImageRecord(
                    dataset=dataset,
                    task=task,
                    label=label,
                    source_group=source_group,
                    source_split="",
                    split=split,
                    source=path,
                    relative_path=path.relative_to(source).as_posix(),
                )
            )


def collect_01(source: Path) -> list[ImageRecord]:
    root = source / "01_uveitis_oct"
    records: list[ImageRecord] = []
    for class_dir in sorted(path for path in root.rglob("*") if path.is_dir()):
        files = [
            path
            for path in image_files(class_dir)
            if path.parent == class_dir
        ]
        if not files:
            continue
        label = class_dir.name
        if label not in {
            "Intermediate+Posterior Uveitis",
            "Normal",
            "Panuveitis",
            "RRD-PVR",
        }:
            continue
        add_class_split(
            records,
            source=source,
            dataset="01_uveitis_oct",
            task="oct_uveitis_4class",
            files=files,
            label=label,
            source_group=f"01_uveitis_oct:{label}",
        )
    return records


def collect_02(source: Path) -> list[ImageRecord]:
    root = source / "02_toxofundus"
    labels_path = root / "dataset_labels.csv"
    images_dir = root / "images"
    with labels_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    available = {path.name: path for path in image_files(images_dir)}
    image_names = set(available)
    label_names = {row["Image name"].strip() for row in rows}
    missing_labels = sorted(label_names - image_names)
    missing_images = sorted(image_names - label_names)
    if missing_labels != ["2809.jpg"] or missing_images != ["2805.jpg"]:
        raise RuntimeError(
            "ToxoFundus filename mismatch changed; review before building: "
            f"missing_labels={missing_labels}, missing_images={missing_images}"
        )

    # The source has one known typo. Keep the mapping explicit and auditable.
    name_aliases = {"2809.jpg": "2805.jpg"}
    by_class: dict[str, list[Path]] = defaultdict(list)
    group_by_path: dict[Path, str] = {}
    for row in rows:
        name = row["Image name"].strip()
        resolved_name = name_aliases.get(name, name)
        path = available.get(resolved_name)
        if path is None:
            raise FileNotFoundError(f"Missing ToxoFundus image for {name}")
        label = "healthy" if row["Label"].strip().lower() == "healthy" else "toxoplasmosis"
        by_class[label].append(path)
        group_by_path[path] = f"02_toxofundus:{row['Source'].strip()}"

    records: list[ImageRecord] = []
    for label, files in sorted(by_class.items()):
        train_files, test_files = split_uv_files(
            files, 0.2, f"02_toxofundus:{label}"
        )
        for split, selected in (("train", train_files), ("test", test_files)):
            for path in selected:
                records.append(
                    ImageRecord(
                        dataset="02_toxofundus",
                        task="fundus_toxo_binary",
                        label=label,
                        source_group=group_by_path[path],
                        source_split="",
                        split=split,
                        source=path,
                        relative_path=path.relative_to(source).as_posix(),
                    )
                )
    return records


def collect_03(source: Path) -> list[ImageRecord]:
    root = source / "03_eye_five_class"
    class_names = {"Cataract", "Conjunctivitis", "Eyelid", "Normal", "Uveitis"}
    records: list[ImageRecord] = []
    seen_hashes: dict[str, Path] = {}
    for class_dir in sorted(path for path in root.rglob("*") if path.is_dir()):
        label = class_dir.name
        if label not in class_names:
            continue
        files = [path for path in image_files(class_dir) if path.parent == class_dir]
        if not files:
            continue
        unique_files: list[Path] = []
        for path in files:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest in seen_hashes:
                continue
            seen_hashes[digest] = path
            unique_files.append(path)
        add_class_split(
            records,
            source=source,
            dataset="03_eye_five_class",
            task="eye_five_class",
            files=unique_files,
            label=label,
            source_group=f"03_eye_five_class:{label}",
        )
    return records


def collect_zhang(source: Path, per_class: int) -> list[ImageRecord]:
    root = source / "13_zhanglab" / "ZhangLabData" / "CellData" / "OCT"
    records: list[ImageRecord] = []
    for split_name in ("train", "test"):
        split_root = root / split_name
        if not split_root.is_dir():
            raise FileNotFoundError(f"Missing ZhangLab OCT directory: {split_root}")
        for class_dir in sorted(path for path in split_root.iterdir() if path.is_dir()):
            files = image_files(class_dir)
            ranked = sorted(
                files,
                key=lambda path: stable_rank(path.as_posix(), f"zhang:{split_name}:{class_dir.name}"),
            )
            limit = per_class if split_name == "train" else min(per_class // 2, 250)
            for path in ranked[:limit]:
                records.append(
                    ImageRecord(
                        dataset=OCT_AUX_NAME,
                        task="oct_aux_4class",
                        label=class_dir.name,
                        source_group=f"13_zhanglab:{class_dir.name}",
                        source_split=split_name,
                        split="train" if split_name == "train" else "test",
                        source=path,
                        relative_path=path.relative_to(source).as_posix(),
                    )
                )
    return records


def read_first_xlsx_rows(path: Path) -> list[list[str]]:
    """Read one XLSX sheet without adding pandas/openpyxl to the data build."""
    with zipfile.ZipFile(path) as archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall("m:si", XLSX_NS):
                shared.append(
                    "".join(
                        node.text or ""
                        for node in item.findall(".//m:t", XLSX_NS)
                    )
                )
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        rows: list[list[str]] = []
        for row in sheet.findall(".//m:row", XLSX_NS):
            values: list[str] = []
            for cell in row.findall("m:c", XLSX_NS):
                value = cell.find("m:v", XLSX_NS)
                inline = cell.find("m:is/m:t", XLSX_NS)
                if cell.get("t") == "s" and value is not None:
                    values.append(shared[int(value.text or "")])
                elif inline is not None:
                    values.append(inline.text or "")
                else:
                    values.append(value.text or "" if value is not None else "")
            rows.append(values)
    return rows


def collect_open_uwf(source: Path) -> list[ImageRecord]:
    """Add the 7-class UWF task with diagnosis-scoped patient groups."""
    root = source / UWF_NAME
    demographics = root / "Demographics of the participants.xlsx"
    image_root = root / "Original UWF Image"
    rows = read_first_xlsx_rows(demographics)
    headers = [value.strip() for value in rows[0]]
    required = {"Image ID", "Patient ID", "Diagnosis"}
    missing_columns = sorted(required - set(headers))
    if missing_columns:
        raise ValueError(
            f"Open UWF demographics missing columns: {missing_columns}"
        )
    images = {path.name: path for path in image_files(image_root)}
    metadata: dict[str, dict[str, str]] = {}
    for raw in rows[1:]:
        padded = [*raw, *("" for _ in range(len(headers) - len(raw)))]
        record = {
            key: value.strip()
            for key, value in zip(headers, padded, strict=False)
        }
        metadata[record["Image ID"]] = record
    if len(metadata) != 700 or set(metadata) != set(images):
        raise ValueError("Open UWF image and demographics inventories differ")

    groups: dict[str, dict[str, list[Path]]] = defaultdict(
        lambda: defaultdict(list)
    )
    group_by_path: dict[Path, str] = {}
    for image_name, record in metadata.items():
        label = record["Diagnosis"]
        path = images[image_name]
        if label not in UWF_LABELS or path.parent.name != label:
            raise ValueError(f"Unexpected Open UWF label for {image_name}")
        group = f"{UWF_NAME}:{label}:{record['Patient ID']}"
        groups[label][group].append(path)
        group_by_path[path] = group

    records: list[ImageRecord] = []
    for label in UWF_LABELS:
        for group, paths in sorted(groups[label].items()):
            bucket = int(
                stable_rank(group, "open-uwf-patient-groups")[:8], 16
            )
            split = "test" if bucket % 10 == 0 else "train"
            for path in sorted(paths, key=lambda item: item.name):
                records.append(
                    ImageRecord(
                        dataset=UWF_NAME,
                        task="uwf_7class",
                        label=label,
                        source_group=group,
                        source_split="",
                        split=split,
                        source=path,
                        relative_path=path.relative_to(source).as_posix(),
                    )
                )
    return records


def collect_rfmid(source: Path) -> tuple[list[ImageRecord], list[dict[str, str]]]:
    root = source / "06_rfmid2"
    records: list[ImageRecord] = []
    label_rows: list[dict[str, str]] = []
    split_map = {
        "Training_set": "train",
        "Validation_set": "validation",
        "Test_set": "test",
    }
    excluded: dict[str, dict[str, list[str]]] = {}
    for source_split in RFMID_SPLITS:
        split_root = root / source_split
        csv_files = sorted(split_root.glob("*labels.csv"))
        if len(csv_files) != 1:
            raise FileNotFoundError(f"Expected one RFMiD labels CSV in {split_root}")
        with csv_files[0].open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
            rows = list(csv.DictReader(handle))
        available = {
            path.stem: path
            for path in image_files(split_root)
        }
        labeled_ids = {
            (row.get("ID") or "").strip()
            for row in rows
            if (row.get("ID") or "").strip()
        }
        missing_ids = sorted(labeled_ids - set(available), key=int)
        extra_ids = sorted(set(available) - labeled_ids, key=int)
        excluded[source_split] = {
            "label_ids_without_image": missing_ids,
            "images_without_label": extra_ids,
        }
        for row in rows:
            image_id = (row.get("ID") or "").strip()
            if not image_id:
                continue
            path = available.get(image_id)
            if path is None:
                continue
            records.append(
                ImageRecord(
                    dataset="06_rfmid2",
                    task="fundus_rfmid_multilabel",
                    label="",
                    source_group=f"06_rfmid2:{image_id}",
                    source_split=source_split,
                    split=split_map[source_split],
                    source=path,
                    relative_path=path.relative_to(source).as_posix(),
                )
            )
            label_rows.append(
                {
                    "split": split_map[source_split],
                    "image": path.relative_to(source).as_posix(),
                    **{key: value for key, value in row.items() if key is not None},
                }
            )
    expected_exclusions = {
        "Training_set": {
            "label_ids_without_image": ["89", "216"],
            "images_without_label": ["79", "222"],
        },
        "Validation_set": {
            "label_ids_without_image": [],
            "images_without_label": [],
        },
        "Test_set": {
            "label_ids_without_image": ["151", "191", "405", "490"],
            "images_without_label": ["251", "291", "404", "489"],
        },
    }
    if excluded != expected_exclusions:
        raise RuntimeError(
            "RFMiD label/image alignment changed; review before building. "
            f"excluded={excluded}"
        )
    for row in label_rows:
        row["excluded_rfmid_alignments"] = json.dumps(excluded, ensure_ascii=False)
    return records, label_rows


def collect_odir(source: Path, train_limit: int) -> tuple[list[ImageRecord], list[dict[str, str]]]:
    root = source / "04_odir5k_preprocessed"
    with (root / "full_df.csv").open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    by_patient: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    for row in rows:
        patient_id = row["ID"].strip()
        for eye in ("Left", "Right"):
            filename = row[f"{eye}-Fundus"].strip()
            by_patient[patient_id][filename] = row
    patients = sorted(by_patient, key=lambda value: stable_rank(value, "odir-patients"))

    image_lookup: dict[str, Path] = {}
    for split_dir_name in ("Training Images", "Testing Images"):
        split_dir = root / "ODIR-5K" / "ODIR-5K" / split_dir_name
        if not split_dir.is_dir():
            raise FileNotFoundError(f"Missing ODIR images: {split_dir}")
        for path in image_files(split_dir):
            image_lookup[path.name] = path

    records: list[ImageRecord] = []
    metadata: list[dict[str, str]] = []
    for patient_id in patients:
        filenames = sorted(by_patient[patient_id])
        if len(metadata) + len(filenames) > train_limit:
            break
        for filename in filenames:
            eye = "left" if "_left" in filename.lower() else "right"
            row = by_patient[patient_id][filename]
            path = image_lookup.get(filename)
            if path is None:
                raise FileNotFoundError(f"Missing ODIR image: {filename}")
            relative = path.relative_to(source).as_posix()
            records.append(
                ImageRecord(
                    dataset="04_odir5k",
                    task="fundus_odir_multilabel",
                    label=row["labels"].strip(),
                    source_group=f"04_odir5k:{patient_id}",
                    source_split="",
                    split="train",
                    source=path,
                    relative_path=relative,
                )
            )
            metadata.append(
                {
                    "patient_id": patient_id,
                    "eye": eye,
                    "image": relative,
                    "age": row["Patient Age"].strip(),
                    "sex": row["Patient Sex"].strip(),
                    "diagnostic_keywords": row[f"{eye.capitalize()}-Diagnostic Keywords"].strip(),
                    "labels": ":".join(
                        sorted(
                            {
                                by_patient[patient_id][name]["labels"].strip()
                                for name in filenames
                            }
                        )
                    ),
                }
            )
    if len(metadata) > train_limit:
        raise AssertionError("ODIR selection exceeded the unique-image limit")
    return records, metadata


def write_outputs(
    source: Path,
    output: Path,
    records: Iterable[ImageRecord],
    *,
    rfmid_labels: list[dict[str, str]],
    odir_metadata: list[dict[str, str]],
) -> dict[str, object]:
    records = sorted(records, key=lambda item: (item.dataset, item.task, item.split, item.relative_path))
    if len({record.relative_path for record in records}) != len(records):
        raise AssertionError("Each staged image must have exactly one manifest row")
    output.mkdir(parents=True, exist_ok=True)
    data_dir = output / "data"
    data_dir.mkdir(exist_ok=True)
    referenced_destinations = {
        (data_dir / record.dataset / record.relative_path).resolve()
        for record in records
    }
    for existing in data_dir.rglob("*"):
        if (
            existing.is_file()
            and existing.suffix.lower() in IMAGE_SUFFIXES
            and existing.resolve() not in referenced_destinations
        ):
            existing.unlink()

    manifest_path = output / "manifest.csv"
    split_counts: dict[str, int] = defaultdict(int)
    dataset_counts: dict[str, int] = defaultdict(int)
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        fields = [
            "dataset",
            "task",
            "label",
            "source_group",
            "source_split",
            "split",
            "image",
            "source_image",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            destination = data_dir / record.dataset / record.relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists():
                shutil.copy2(record.source, destination)
            elif destination.stat().st_size != record.source.stat().st_size:
                raise RuntimeError(f"Staging collision: {destination}")
            writer.writerow(
                {
                    "dataset": record.dataset,
                    "task": record.task,
                    "label": record.label,
                    "source_group": record.source_group,
                    "source_split": record.source_split,
                    "split": record.split,
                    "image": destination.relative_to(output).as_posix(),
                    "source_image": record.relative_path,
                }
            )
            split_counts[record.split] += 1
            dataset_counts[record.dataset] += 1

    with (output / "rfmid_labels.csv").open("w", encoding="utf-8", newline="") as handle:
        base_fields = [
            key
            for key in (rfmid_labels[0] if rfmid_labels else ["split", "image"])
            if key != "excluded_rfmid_alignments"
        ]
        fieldnames = base_fields + ["excluded_rfmid_alignments"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rfmid_labels)

    with (output / "odir_metadata.csv").open("w", encoding="utf-8", newline="") as handle:
        fieldnames = list(odir_metadata[0]) if odir_metadata else ["patient_id", "image"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(odir_metadata)

    total_bytes = sum(path.stat().st_size for path in data_dir.rglob("*") if path.is_file())
    summary = {
        "images": len(records),
        "bytes": total_bytes,
        "split_counts": dict(sorted(split_counts.items())),
        "dataset_counts": dict(sorted(dataset_counts.items())),
        "unique_source_groups": len({record.source_group for record in records}),
        "toxofundus_name_alias": {"2809.jpg": "2805.jpg"},
        "notes": [
            "01 has no patient identifiers; its split is dataset-internal.",
            "03 is an SMOTE-derived source and is used for prototype training only.",
            "ODIR left and right eyes stay in the same patient group.",
            "RFMiD keeps the original train/validation/test split.",
            "RFMiD excludes six label/image mismatches with no safe one-to-one mapping.",
            "ZhangLab includes only CellData/OCT, never chest_xray.",
        ],
    }
    with (output / "summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return summary


def main() -> None:
    args = parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    if not source.is_dir():
        raise FileNotFoundError(source)
    if any(source == candidate or source.is_relative_to(candidate) for candidate in (output,)):
        raise ValueError("Output must not contain the source directory")

    records: list[ImageRecord] = []
    records.extend(collect_01(source))
    records.extend(collect_02(source))
    records.extend(collect_03(source))
    records.extend(collect_zhang(source, args.zhang_per_class))
    records.extend(collect_open_uwf(source))
    rfmid_records, rfmid_labels = collect_rfmid(source)
    records.extend(rfmid_records)
    odir_records, odir_metadata = collect_odir(source, args.odir_train)
    records.extend(odir_records)

    summary = write_outputs(
        source,
        output,
        records,
        rfmid_labels=rfmid_labels,
        odir_metadata=odir_metadata,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

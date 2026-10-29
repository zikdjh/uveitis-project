
"""Build a patient-isolated task from the 25-etiologies uveitis matrix.

The matrix lives at docs/Uveites_25_etiologies_group_0626.csv (accented filename
in the repository). Its header carries 153 columns and the final column is the
dependent variable ("Etiology"); every other column is an independent variable.

This script does four things and nothing else:

1. validates the shape (header present, last column is Etiology, at least one
   data row);
2. requires patient_id and eye columns when --require-patient is set, so the
   split can be patient isolated instead of row isolated;
3. assigns every patient to exactly one split with a deterministic SHA-256
   hash, so reruns are reproducible and no patient crosses splits;
4. writes dataset.csv plus audit.json for downstream training.

It never fabricates rows, never imputes missing labels, and never copies
anything that is not already in the working tree.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INPUT = PROJECT_ROOT / "docs" / "Uv\u00e9ites_25_etiologies_group_0626.csv"
DEFAULT_OUTPUT = (
    PROJECT_ROOT / "model/training" / "datasets" / "tasks" / "uveitis_etiology_25"
)

TARGET_COLUMN = "Etiology"
PATIENT_COLUMN = "patient_id"
EYE_COLUMN = "eye"

# Split ratios for patients, not rows. Deterministic per patient id.
SPLIT_BUCKETS = (("train", 70), ("validation", 15), ("test", 15))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--require-patient",
        action="store_true",
        help="fail unless patient_id and eye columns are present",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="only run the shape checks; write nothing",
    )
    return parser.parse_args()


def _read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        header = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]
    return header, rows


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate(
    path: Path,
    header: list[str],
    rows: list[dict[str, str]],
    require_patient: bool,
) -> list[str]:
    errors: list[str] = []
    if not path.is_file():
        errors.append(f"input file not found: {path}")
        return errors
    if not header:
        errors.append("header row is missing or unreadable")
        return errors
    if header[-1] != TARGET_COLUMN:
        errors.append(f"last column must be {TARGET_COLUMN!r}, found {header[-1]!r}")
    if not rows:
        errors.append(
            f"matrix has {len(header)} columns but 0 data rows; "
            "export the case rows before training"
        )
        return errors
    if require_patient:
        for column in (PATIENT_COLUMN, EYE_COLUMN):
            if column not in header:
                errors.append(
                    f"column {column!r} is required for a patient-isolated split"
                )
    labels = [str(row.get(TARGET_COLUMN) or "").strip() for row in rows]
    blank = sum(1 for label in labels if not label)
    if blank:
        errors.append(f"{blank} row(s) have an empty {TARGET_COLUMN}")
    if len(set(labels)) < 2:
        errors.append(
            f"{TARGET_COLUMN} needs at least two classes, "
            f"found {sorted(set(labels))!r}"
        )
    return errors


def _split_for(patient_key: str) -> str:
    digest = hashlib.sha256(patient_key.encode("utf-8")).hexdigest()
    bucket = int(digest[:8], 16) % 100
    cumulative = 0
    for name, weight in SPLIT_BUCKETS:
        cumulative += weight
        if bucket < cumulative:
            return name
    return SPLIT_BUCKETS[-1][0]


def main() -> int:
    args = _parse_args()
    input_path: Path = args.input

    if not input_path.is_file():
        print(f"FAIL: input file not found: {input_path}", file=sys.stderr)
        return 2

    header, rows = _read_rows(input_path)
    errors = _validate(input_path, header, rows, args.require_patient)
    if errors:
        for message in errors:
            print(f"FAIL: {message}", file=sys.stderr)
        return 2

    if args.validate_only:
        print(
            f"OK: {len(rows)} row(s), {len(header)} column(s), "
            f"target={TARGET_COLUMN}"
        )
        return 0

    # Patient key falls back to the row index so a row-isolated file still
    # produces a usable, clearly labelled manifest.
    patient_keys: list[str] = []
    for index, row in enumerate(rows):
        explicit = str(row.get(PATIENT_COLUMN) or "").strip()
        patient_keys.append(explicit or f"row-{index:05d}")

    splits = [_split_for(key) for key in patient_keys]

    output_dir: Path = args.output
    output_dir.mkdir(parents=True, exist_ok=True)

    dataset_path = output_dir / "dataset.csv"
    out_header = ["row_id", "patient_key", "split", *header]
    with dataset_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(out_header)
        for index, row in enumerate(rows):
            writer.writerow(
                [
                    f"row-{index:05d}",
                    patient_keys[index],
                    splits[index],
                    *[row.get(column, "") for column in header],
                ]
            )

    split_counts = Counter(splits)
    label_counts: dict[str, Counter] = defaultdict(Counter)
    patients_per_split: dict[str, set] = defaultdict(set)
    rows_per_patient: Counter = Counter()
    for index, row in enumerate(rows):
        label = str(row.get(TARGET_COLUMN) or "").strip()
        label_counts[splits[index]][label] += 1
        patients_per_split[splits[index]].add(patient_keys[index])
        rows_per_patient[patient_keys[index]] += 1

    shared_patients = [key for key, count in rows_per_patient.items() if count > 1]

    audit = {
        "task": "uveitis_etiology_25",
        "input": {
            "path": str(input_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "sha256": _sha256_file(input_path),
            "bytes": input_path.stat().st_size,
        },
        "shape": {
            "columns": len(header),
            "data_rows": len(rows),
            "target_column": header[-1],
            "feature_columns": len(header) - 1,
        },
        "patient_isolation": {
            "explicit_patient_column": PATIENT_COLUMN in header,
            "distinct_patient_keys": len(rows_per_patient),
            "patients_with_multiple_rows": len(shared_patients),
            "note": (
                "patient_id present; splits are grouped by patient"
                if PATIENT_COLUMN in header
                else "patient_id absent; split falls back to per-row keys and "
                "must not be reported as patient level"
            ),
        },
        "splits": {
            name: {
                "rows": split_counts.get(name, 0),
                "patients": len(patients_per_split.get(name, set())),
                "labels": dict(label_counts.get(name, Counter())),
            }
            for name, _ in SPLIT_BUCKETS
        },
        "label_total": dict(
            Counter(str(row.get(TARGET_COLUMN) or "").strip() for row in rows)
        ),
        "artifacts": {"dataset": "dataset.csv"},
    }
    (output_dir / "audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(
        f"OK: wrote {dataset_path} with {len(rows)} row(s) across "
        f"{len(rows_per_patient)} patient key(s)"
    )
    for name, weight in SPLIT_BUCKETS:
        print(
            f"  {name}: rows={split_counts.get(name, 0)} "
            f"patients={len(patients_per_split.get(name, set()))}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


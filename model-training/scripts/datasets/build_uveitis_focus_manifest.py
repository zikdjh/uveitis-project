"""Build the 2026-10-27 doctor-label + patient-isolated uveitis focus manifest.

The manifest combines the two label sources confirmed in the open-data audit:

* ``02_toxofundus`` -> ``fundus_toxo_binary`` (ocular toxoplasmosis, labels
  assigned by ophthalmologists, no patient identifiers).
* ``14_open_uwf700`` -> ``uwf_uveitis_binary`` (ultrawidefield uveitis vs
  non-uveitis, patient-isolated groups).

The consumed Open UWF test split (90 rows / 78 patient groups, already
evaluated once) is deliberately excluded so it is never reused. Only the
Open UWF training rows are carried over; the trainer re-holds its own
validation groups from those rows.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
MAIN_MANIFEST = (
    PROJECT_ROOT / "model-training" / "datasets" / "training" / "manifest.csv"
)
UWF_MANIFEST = (
    PROJECT_ROOT
    / "model-training"
    / "datasets"
    / "tasks"
    / "open_uwf_uveitis_binary"
    / "manifest.csv"
)
OUTPUT = (
    PROJECT_ROOT
    / "model-training"
    / "datasets"
    / "tasks"
    / "uveitis_focus_20261027"
)

CONSUMED_UWF_TEST_RUN = "uwf-binary-eval-test-20261026-01"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    return parser.parse_args()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _group_key(row: dict[str, str]) -> str:
    if row["dataset"] == "02_toxofundus":
        return f"02:{row['source_image']}"
    if row["dataset"] == "14_open_uwf700":
        return f"14:{row['source_group']}"
    return f"{row['dataset']}:{row['source_group']}:{row['source_image']}"


def main() -> int:
    args = _parse_args()
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")

    main_rows = _read(MAIN_MANIFEST)
    uwf_rows = _read(UWF_MANIFEST)

    toxo = [row for row in main_rows if row["dataset"] == "02_toxofundus"]
    if len(toxo) != 412:
        raise ValueError(f"Expected 412 toxo rows, got {len(toxo)}")

    uwf_train = [row for row in uwf_rows if row["split"] == "train"]
    uwf_test = [row for row in uwf_rows if row["split"] == "test"]
    uwf_validation = [row for row in uwf_rows if row["split"] == "validation"]
    if len(uwf_train) != 503 or len(uwf_test) != 90:
        raise ValueError(
            f"Unexpected UWF split sizes: train={len(uwf_train)} test={len(uwf_test)}"
        )

    combined = toxo + uwf_train
    fields = list(combined[0])
    for row in combined:
        if list(row) != fields:
            raise ValueError("Row field order differs from the header")

    # Patient/group isolation checks.
    toxo_train_groups = {_group_key(r) for r in toxo if r["split"] == "train"}
    toxo_test_groups = {_group_key(r) for r in toxo if r["split"] == "test"}
    if toxo_train_groups & toxo_test_groups:
        raise AssertionError("Toxo train/test group overlap")
    uwf_train_groups = {_group_key(r) for r in uwf_train}
    uwf_test_groups = {_group_key(r) for r in uwf_test}
    consumed_overlap = sorted(uwf_train_groups & uwf_test_groups)
    if consumed_overlap:
        raise AssertionError(
            f"UWF train rows overlap the consumed test groups: {consumed_overlap[:3]}"
        )

    output.mkdir(parents=True)
    manifest_path = output / "manifest.csv"
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(combined)

    audit = {
        "status": "ok",
        "task_dir": "model-training/datasets/tasks/uveitis_focus_20261027",
        "rows": len(combined),
        "split_counts": dict(sorted(Counter(r["split"] for r in combined).items())),
        "task_counts": dict(sorted(Counter(r["task"] for r in combined).items())),
        "task_split_counts": dict(
            sorted(Counter(f"{r['task']}::{r['split']}" for r in combined).items())
        ),
        "label_counts": dict(
            sorted(Counter(f"{r['task']}::{r['label']}" for r in combined).items())
        ),
        "patient_groups": {
            "toxo_train": len(toxo_train_groups),
            "toxo_test": len(toxo_test_groups),
            "uwf_train": len(uwf_train_groups),
        },
        "toxo_train_test_group_overlap": 0,
        "uwf_train_vs_consumed_test_group_overlap": 0,
        "excluded_consumed_rows": {
            "uwf_test": len(uwf_test),
            "uwf_validation": len(uwf_validation),
            "run": CONSUMED_UWF_TEST_RUN,
        },
        "manifest_sha256": _sha256(manifest_path),
        "source_manifest_sha256": {
            "training/manifest.csv": _sha256(MAIN_MANIFEST),
            "tasks/open_uwf_uveitis_binary/manifest.csv": _sha256(UWF_MANIFEST),
        },
        "note": (
            "ToxoFundus supplies doctor-assigned labels without patient IDs; "
            "Open UWF supplies patient-isolated groups. The Open UWF test and "
            "validation rows are excluded because that patient-isolated test "
            "split was already evaluated once and must not be reused."
        ),
    }
    (output / "audit.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(audit, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

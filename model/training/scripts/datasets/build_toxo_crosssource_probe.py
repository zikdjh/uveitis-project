"""Build a cross-source specificity probe for the toxoplasmosis binary adapter.

The activity task has no obtainable patient-isolated, doctor-confirmed
external set, so an external *sensitivity* claim cannot be made. This probe
answers the remaining honest question instead: when the frozen
``fundus_toxo_binary`` adapter sees normal fundus photographs from a completely
different institution, how often does it call them toxoplasmosis?

Source data is ``04_odir5k`` (ODIR-5K), which is staged but has never been
trained on and has never been evaluated: the ``fundus_odir_multilabel`` task is
not registered in ``PHASE1_TASKS``. Only rows labelled ``['N']`` (normal) are
used, and whole patient groups are sampled so left/right eyes of one patient
never split across a boundary.

The probe reuses the ``fundus_toxo_binary`` task and its ``healthy`` label so
the frozen adapter's own prompt and label parser apply unchanged. Every sampled
row is written with ``split=test`` and is consumed by the single evaluation.

This is a specificity-only, image-level cross-source probe. It is not patient-
isolated validation, not an external sensitivity claim, and ODIR ``N`` means its
eight target diseases are absent.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
TRAINING_MANIFEST = (
    PROJECT_ROOT / "model/training" / "datasets" / "training" / "manifest.csv"
)
OUTPUT = (
    PROJECT_ROOT
    / "model/training"
    / "datasets"
    / "tasks"
    / "fundus_toxo_crosssource_probe"
)

DATASET = "04_odir5k"
NORMAL_LABEL = "['N']"
PROBE_TASK = "fundus_toxo_binary"
PROBE_LABEL = "healthy"
DEFAULT_PATIENTS = 150
DEFAULT_SEED = 20261028


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--patients", type=int, default=DEFAULT_PATIENTS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    return parser.parse_args()


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
        raise FileExistsError(f"Output already exists: {output}")
    if args.patients < 1:
        raise ValueError("--patients must be positive")

    with TRAINING_MANIFEST.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]

    normal_rows = [
        row
        for row in rows
        if row["dataset"] == DATASET and row["label"] == NORMAL_LABEL
    ]
    if not normal_rows:
        raise ValueError("No ODIR normal rows found in the staged manifest")

    by_patient: dict[str, list[dict]] = defaultdict(list)
    for row in normal_rows:
        by_patient[row["source_group"]].append(row)
    groups = {key: value for key, value in by_patient.items()}
    if args.patients > len(groups):
        raise ValueError(
            f"Requested {args.patients} patients but only {len(groups)} are available"
        )

    rng = random.Random(args.seed)
    selected_groups = sorted(groups)
    rng.shuffle(selected_groups)
    selected_groups = sorted(selected_groups[: args.patients])

    selected_rows: list[dict] = []
    for group in selected_groups:
        selected_rows.extend(
            sorted(groups[group], key=lambda item: item["source_image"])
        )
    selected_rows.sort(key=lambda item: (item["source_group"], item["source_image"]))

    probe_rows = [
        {
            **{key: row[key] for key in fields},
            "task": PROBE_TASK,
            "label": PROBE_LABEL,
            "split": "test",
        }
        for row in selected_rows
    ]
    for row in probe_rows:
        if list(row) != fields:
            raise ValueError("Row field order differs from the header")

    if len({row["source_image"] for row in probe_rows}) != len(probe_rows):
        raise ValueError("Duplicate images in the probe")
    if any(row["dataset"] != DATASET for row in probe_rows):
        raise ValueError("Probe picked up a non-ODIR row")

    eyes = Counter(
        Path(row["source_image"]).stem.rsplit("_", 1)[-1] for row in probe_rows
    )

    output.mkdir(parents=True)
    manifest_path = output / "manifest.csv"
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(probe_rows)

    audit = {
        "status": "ok",
        "probe": "fundus_toxo_crosssource_probe",
        "task_dir": "model/training/datasets/tasks/fundus_toxo_crosssource_probe",
        "source": "model/training/datasets/training/manifest.csv (dataset 04_odir5k)",
        "source_dataset": "ODIR-5K",
        "source_license": "CC BY 4.0 (ODIR-5K, paloalto / Chinese hospital consortium release)",
        "probe_task": PROBE_TASK,
        "probe_label": PROBE_LABEL,
        "purpose": "cross_source_specificity_only",
        "patients_available": len(groups),
        "patients_sampled": len(selected_groups),
        "rows": len(probe_rows),
        "eye_counts": dict(sorted(eyes.items())),
        "patient_group_prefix_counts": dict(
            sorted(Counter(row["source_group"].split(":")[0] for row in probe_rows).items())
        ),
        "sample_seed": args.seed,
        "odir_normal_rows_available": len(normal_rows),
        "odir_train_task_registered": False,
        "odir_rows_previously_trained": False,
        "odir_rows_previously_evaluated": False,
        "patient_id_available": True,
        "patient_isolated_sampling": True,
        "external_validation_claim": "prohibited_no_external_positives",
        "claim_scope": "cross_source_false_positive_rate_only",
        "source_manifest_sha256": _sha256(TRAINING_MANIFEST),
        "manifest_sha256": _sha256(manifest_path),
        "note": (
            "Normal ODIR fundus photographs relabelled as the healthy class of "
            "the frozen fundus_toxo_binary adapter. Sampling is by whole patient "
            "group, but the read-out is an image-level false-positive rate, not "
            "patient-isolated validation and not an external sensitivity claim. "
            "ODIR 'N' means the eight ODIR target diseases are absent; it is not "
            "a guarantee of a pathology-free eye. These rows are consumed by the "
            "single probe evaluation."
        ),
    }
    (output / "audit.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(audit, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

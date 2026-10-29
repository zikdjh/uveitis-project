"""Link the 01_uveitis_oct images to their clinical companion tables.

The 75 OCT images in ``01_uveitis_oct`` ship without any patient metadata.
Figshare ``22632715`` provides exactly 75 clinical rows
(PVR 19 / Intermediate+Posterior Uveitis 12 / Panuveitis 16 / Normal 28) and
figshare ``32054064`` is unrelated corneal-endothelium data.

This script builds an explicit, auditable image -> clinical-row mapping. The
link is *inferred* from the per-category image index (``Normal 7.jpeg`` ->
7th Normal clinical row), so every row is tagged with its mapping confidence
and the audit states the assumption. It writes a metadata table only; it does
not copy images or claim patient-level isolation.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
EXTRACTED = PROJECT_ROOT / "model/training" / "datasets" / "extracted"
IMAGE_ROOT = (
    EXTRACTED
    / "01_uveitis_oct"
    / "Optical Coherence Tomography (OCT) Images of Proliferative Vitreoretinopathy, Uveitis, and Normal Eyes"
)
COMBINED_CSV = (
    EXTRACTED
    / "19_figshare_uveitis_clinical_tables"
    / "characteristics_pvr_uveitis_normal.csv"
)
UVEITIS_CSV = (
    EXTRACTED
    / "19_figshare_uveitis_clinical_tables"
    / "characteristics_uveitis_patients.csv"
)
OUTPUT_DIR = PROJECT_ROOT / "model/training" / "datasets" / "tasks" / "oct_uveitis_clinical"

DATASET = "01_uveitis_oct"
TASK = "oct_uveitis_clinical"

# Per-category image index -> (label, combined-CSV row offset).
# The offsets follow the published clinical-table order.
CATEGORY_LAYOUT = {
    "RRD-PVR": ("Proliferative Vitreoretinopathy", 0, 19),
    "Intermediate+Posterior Uveitis": ("Intermediate-Posterior Uveitis", 19, 12),
    "Panuveitis": ("Panuveitis", 31, 16),
    "Normal": ("Normal", 47, 28),
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR)
    return parser.parse_args()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = []
        for row in csv.DictReader(handle):
            row = {(k or "").strip(): (v or "").strip() for k, v in row.items()}
            number = row.get("Number", "")
            if number.isdigit():
                rows.append(row)
    return rows


def _image_index(name: str) -> int:
    stem = Path(name).stem
    digits = "".join(ch for ch in stem if ch.isdigit())
    if not digits:
        raise ValueError(f"Cannot read category index from image name: {name}")
    return int(digits)


def main() -> int:
    args = _parse_args()
    output = args.output.resolve()

    combined = _read_rows(COMBINED_CSV)
    uveitis = _read_rows(UVEITIS_CSV)
    if len(combined) != 75:
        raise ValueError(f"Expected 75 clinical rows, got {len(combined)}")
    if len(uveitis) != 28:
        raise ValueError(f"Expected 28 uveitis rows, got {len(uveitis)}")

    counts = Counter(row["Diagnosis"] for row in combined)
    expected = {
        "Proliferative Vitreoretinopathy": 19,
        "Intermediate-Posterior Uveitis": 12,
        "Panuveitis": 16,
        "Normal": 28,
    }
    if dict(counts) != expected:
        raise ValueError(f"Unexpected clinical diagnosis counts: {dict(counts)}")

    # The uveitis table must align with combined rows 20..47.
    for offset, row in enumerate(uveitis, start=1):
        reference = combined[19 + offset - 1]
        if (row["Age"], row["Sex"], row["Diagnosis"]) != (
            reference["Age"],
            reference["Sex"],
            reference["Diagnosis"],
        ):
            raise ValueError(
                f"Uveitis row {offset} does not align with combined row "
                f"{19 + offset}: {row} vs {reference}"
            )

    image_rows: list[dict[str, str]] = []
    for category, (label, offset, size) in CATEGORY_LAYOUT.items():
        directory = IMAGE_ROOT / category
        images = sorted(
            (p for p in directory.iterdir() if p.is_file()),
            key=lambda p: _image_index(p.name),
        )
        if len(images) != size:
            raise ValueError(f"{category}: expected {size} images, got {len(images)}")
        for image in images:
            index = _image_index(image.name)
            if not 1 <= index <= size:
                raise ValueError(f"{image.name}: index {index} outside 1..{size}")
            clinical = combined[offset + index - 1]
            if clinical["Diagnosis"] != label:
                raise ValueError(
                    f"{image.name}: clinical row {clinical['Number']} is "
                    f"{clinical['Diagnosis']}, expected {label}"
                )
            image_rows.append(
                {
                    "dataset": DATASET,
                    "task": TASK,
                    "image": f"data/{image.name}",
                    "source_image": image.name,
                    "category": category,
                    "clinical_row": clinical["Number"],
                    "age": clinical["Age"],
                    "sex": clinical["Sex"],
                    "visual_acuity": clinical["Visual Acuity"],
                    "vit_rpe_intensity": clinical["VIT/RPE-Relative Intensity"],
                    "etiology": "",
                    "patient_proxy_key": "",
                    "mapping_confidence": "inferred_from_category_index",
                }
            )

    # Attach etiology for the two uveitis categories from the uveitis table.
    uveitis_by_diagnosis: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in uveitis:
        uveitis_by_diagnosis[row["Diagnosis"]].append(row)
    counter_by_diagnosis: Counter[str] = Counter()
    for row in image_rows:
        label = CATEGORY_LAYOUT[row["category"]][0]
        if label in uveitis_by_diagnosis:
            source = uveitis_by_diagnosis[label][counter_by_diagnosis[label]]
            counter_by_diagnosis[label] += 1
            row["etiology"] = source["Etiology"]

    # Group eyes that share the same category + age + sex as a *proxy* for a
    # patient (contrast this with per-eye keys; it is not confirmed identity).
    buckets: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in image_rows:
        buckets[(row["category"], row["age"], row["sex"])].append(row)
    proxy_groups = 0
    for (category, age, sex), rows in buckets.items():
        key = f"01:{category}:{age}:{sex}"
        for row in rows:
            row["patient_proxy_key"] = key
        if len(rows) > 1:
            proxy_groups += 1

    output.mkdir(parents=True, exist_ok=True)
    fields = list(image_rows[0])
    manifest_path = output / "clinical-link.csv"
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(image_rows)

    audit = {
        "status": "ok",
        "task": TASK,
        "images": len(image_rows),
        "category_counts": dict(sorted(Counter(r["category"] for r in image_rows).items())),
        "clinical_rows_used": len(combined),
        "etiology_labeled_images": sum(1 for r in image_rows if r["etiology"]),
        "etiology_counts": dict(
            sorted(Counter(r["etiology"] for r in image_rows if r["etiology"]).items())
        ),
        "proxy_patient_groups_shared": proxy_groups,
        "mapping_rule": "per-category image index N -> Nth clinical row of that diagnosis",
        "mapping_confidence": "inferred",
        "mapping_validated_by": [
            "category counts match the published clinical table exactly (19/12/16/28)",
            "uveitis table age/sex/diagnosis matches combined rows 20..47",
        ],
        "patient_isolation": "not_confirmed",
        "external_validation_claim": "prohibited",
        "clinical_link_sha256": _sha256(manifest_path),
        "source_sha256": {
            "characteristics_pvr_uveitis_normal.csv": _sha256(COMBINED_CSV),
            "characteristics_uveitis_patients.csv": _sha256(UVEITIS_CSV),
        },
        "note": (
            "The image->clinical link is inferred from the per-category index "
            "and must be confirmed with the data authors before it is used for "
            "patient-level grouping. Etiology labels for the 28 uveitis eyes "
            "are as printed in the published clinical table."
        ),
    }
    (output / "audit.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(audit, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

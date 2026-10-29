"""Read-only inventory for the Modal training data volume."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import modal


app = modal.App("uveitis-inspect-data")
data_volume = modal.Volume.from_name("uveitis-data", create_if_missing=True)


@app.function(volumes={"/data": data_volume})
def inspect_data() -> str:
    root = Path("/data")
    payload_root = root / "data"
    manifest_path = payload_root / "manifest.csv"
    with manifest_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    missing = [
        row["image"]
        for row in rows
        if not (payload_root / row["image"]).is_file()
    ]
    datasets = Counter(row["dataset"] for row in rows)
    splits = Counter(row["split"] for row in rows)
    image_files = [
        path
        for path in (payload_root / "data").rglob("*")
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}
    ]
    return json.dumps(
        {
            "manifest_rows": len(rows),
            "manifest_unique_images": len({row["image"] for row in rows}),
            "image_files": len(image_files),
            "missing_manifest_files": len(missing),
            "missing_examples": missing[:10],
            "datasets": dict(sorted(datasets.items())),
            "splits": dict(sorted(splits.items())),
            "bytes": sum(path.stat().st_size for path in image_files),
        },
        indent=2,
        ensure_ascii=False,
    )


@app.local_entrypoint()
def main() -> None:
    print(inspect_data.remote())

"""Read-only model-volume inventory without importing training helpers."""

from __future__ import annotations

import json
from pathlib import Path

import modal


app = modal.App("uveitis-list-models")
models_volume = modal.Volume.from_name("uveitis-models", create_if_missing=True)


@app.function(volumes={"/models": models_volume})
def list_models() -> str:
    root = Path("/models")
    files = [
        {
            "path": str(path.relative_to(root)),
            "bytes": path.stat().st_size,
        }
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".cache" not in path.parts
    ]
    return json.dumps(
        {
            "files": files,
            "total_files": len(files),
            "total_bytes": sum(item["bytes"] for item in files),
            "models": sorted(
                str(path.relative_to(root))
                for path in root.rglob("*")
                if path.is_file() and path.suffix == ".safetensors"
            ),
        },
        indent=2,
        ensure_ascii=False,
    )


@app.local_entrypoint()
def main() -> None:
    print(list_models.remote())

"""Inspect the path layout visible from a mounted Modal data volume."""

from __future__ import annotations

import json
from pathlib import Path

import modal


app = modal.App("uveitis-volume-path-probe")
data_volume = modal.Volume.from_name("uveitis-data", create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="3.11")
    .add_local_file(
        Path(__file__).with_name("modal_volumes.py"),
        remote_path="/root/modal_volumes.py",
        copy=True,
    )
)


@app.function(image=image, volumes={"/data": data_volume}, timeout=5 * 60)
def probe() -> str:
    data_volume.reload()
    roots = []
    for value in ("/data", "/data/data", "/data/data/data"):
        root = Path(value)
        if not root.is_dir():
            roots.append({"path": value, "exists": False})
            continue
        entries = []
        for path in sorted(root.iterdir())[:20]:
            entries.append(
                {
                    "name": path.name,
                    "is_dir": path.is_dir(),
                    "is_file": path.is_file(),
                }
            )
        roots.append({"path": value, "exists": True, "entries": entries})
    target = Path(
        "/data/data/data/01_uveitis_oct/01_uveitis_oct/"
        "Optical Coherence Tomography (OCT) Images of Proliferative "
        "Vitreoretinopathy, Uveitis, and Normal Eyes/"
        "Intermediate+Posterior Uveitis/Int+Post Uveitis 1.jpeg"
    )
    parents = []
    current = target
    while str(current) != "/":
        parents.append(
            {
                "path": str(current),
                "exists": current.exists(),
                "is_file": current.is_file(),
                "is_dir": current.is_dir(),
            }
        )
        current = current.parent
    return json.dumps(
        {"roots": roots, "target": str(target), "parents": parents},
        indent=2,
        ensure_ascii=False,
    )


@app.local_entrypoint()
def main() -> None:
    print(probe.remote())

#!/usr/bin/env python3
"""Pull the existing Qwen3.5-4B model volume into the training directory."""

from __future__ import annotations

import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
TARGET = ROOT / "model-training" / "models" / "qwen" / "Qwen3.5-4B"
MODAL = ROOT / "model-training" / ".venv-modal" / "Scripts" / "modal.exe"


def verify(target: Path) -> dict[str, object]:
    index_path = target / "model.safetensors.index.json"
    if not index_path.is_file():
        raise RuntimeError(f"Missing weight index: {index_path}")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    shards = sorted(set(index["weight_map"].values()))
    details = []
    for shard in shards:
        path = target / shard
        if not path.is_file():
            raise RuntimeError(f"Missing weight shard: {path}")
        size = path.stat().st_size
        if size == 0:
            raise RuntimeError(f"Empty weight shard: {path}")
        with path.open("rb") as stream:
            header_bytes = struct.unpack("<Q", stream.read(8))[0]
        if header_bytes <= 0 or header_bytes >= size:
            raise RuntimeError(f"Invalid safetensors header: {path}")
        details.append({"name": shard, "bytes": size})
    files = [path for path in target.rglob("*") if path.is_file()]
    required = {
        "config.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "preprocessor_config.json",
        "model.safetensors.index.json",
    }
    missing = sorted(name for name in required if not (target / name).is_file())
    if missing:
        raise RuntimeError(f"Missing model files: {', '.join(missing)}")
    return {
        "target": str(target),
        "files": len(files),
        "bytes": sum(path.stat().st_size for path in files),
        "shards": details,
    }


def main() -> int:
    target = TARGET
    target.mkdir(parents=True, exist_ok=True)
    marker = target / "pull-manifest.json"
    if marker.is_file():
        result = verify(target)
        print(json.dumps({"status": "already_present", **result}, indent=2))
        return 0

    if not MODAL.is_file():
        raise RuntimeError(f"Modal CLI not found: {MODAL}")
    with tempfile.TemporaryDirectory(dir=target.parent) as temporary:
        staging = Path(temporary)
        print("Downloading model volume into staging...", flush=True)
        completed = subprocess.run(
            [
                str(MODAL),
                "volume",
                "get",
                "uveitis-models",
                "qwen/Qwen3.5-4B",
                str(staging),
            ],
            cwd=ROOT,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"Modal volume download failed: {completed.returncode}")
        source_root = staging
        nested = staging / "Qwen3.5-4B"
        if nested.is_dir():
            source_root = nested
        for source in sorted(source_root.iterdir()):
            destination = target / source.name
            if destination.exists():
                raise RuntimeError(f"Refusing to overwrite: {destination}")
            source.replace(destination)

    result = verify(target)
    marker.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": "downloaded", **result}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

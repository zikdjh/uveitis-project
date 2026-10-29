"""Copy an evaluated checkpoint's LoRA files into best_adapter/.

This does not train, merge, quantize, or alter model weights. It only promotes
the two PEFT adapter files from a completed checkpoint after validation.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

import modal

from modal_volumes import RUNS_VOLUME_NAME, runs_volume


APP_NAME = "uveitis-promote-best-adapter"
RUN_ID = os.environ.get("UV_RUN_ID", "")
CHECKPOINT_STEP = int(os.environ.get("UV_CHECKPOINT_STEP", "0"))

image = (
    modal.Image.debian_slim(python_version="3.11")
    .add_local_file(
        Path(__file__).with_name("modal_volumes.py"),
        remote_path="/root/modal_volumes.py",
        copy=True,
    )
)
app = modal.App(APP_NAME)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@app.function(
    image=image,
    volumes={"/runs": runs_volume},
    timeout=10 * 60,
)
def promote(options: dict | None = None) -> str:
    global RUN_ID, CHECKPOINT_STEP
    options = options or {}
    RUN_ID = str(options.get("run_id", RUN_ID))
    CHECKPOINT_STEP = int(options.get("checkpoint_step", CHECKPOINT_STEP))
    if not RUN_ID or CHECKPOINT_STEP <= 0:
        raise ValueError("UV_RUN_ID and UV_CHECKPOINT_STEP are required")

    runs_volume.reload()
    run_dir = Path(f"/runs/qwen3.5-4b/{RUN_ID}")
    source_dir = run_dir / "checkpoints" / f"step-{CHECKPOINT_STEP:06d}"
    output_dir = run_dir / "best_adapter"
    output_dir.mkdir(parents=True, exist_ok=True)
    expected_hashes: dict[str, str] = {}
    for name in ("adapter_config.json", "adapter_model.safetensors"):
        source = source_dir / name
        if not source.is_file():
            raise FileNotFoundError(source)
        destination = output_dir / name
        shutil.copy2(source, destination)
        copied_hash = _sha256(destination)
        if copied_hash != _sha256(source):
            raise RuntimeError(f"Hash mismatch after copying {source}")
        expected_hashes[name] = copied_hash

    checkpoint_file = source_dir / "checkpoint.json"
    checkpoint = (
        json.loads(checkpoint_file.read_text(encoding="utf-8"))
        if checkpoint_file.is_file()
        else {}
    )
    manifest = {
        "run_id": RUN_ID,
        "step": CHECKPOINT_STEP,
        "validation_loss": checkpoint.get("validation_loss"),
        "source_checkpoint": str(source_dir),
        "adapter_dir": str(output_dir),
        "adapter_sha256": expected_hashes,
        "operation": "copy_adapter_files_only",
        "weights_modified": False,
        "volume": RUNS_VOLUME_NAME,
        "created_at": datetime.now(UTC).isoformat(),
    }
    (output_dir / "adapter_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    runs_volume.commit()
    return json.dumps(manifest, indent=2, ensure_ascii=False)


@app.local_entrypoint()
def main() -> None:
    options = {
        key: os.environ[env_name]
        for key, env_name in {
            "run_id": "UV_RUN_ID",
            "checkpoint_step": "UV_CHECKPOINT_STEP",
        }.items()
        if env_name in os.environ
    }
    print(promote.remote(options))

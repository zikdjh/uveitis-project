"""Download model weights into the persistent Modal models volume.

Run:

    modal run model/training/code/training/modal_prepare_models.py

This downloads both models from Hugging Face. It does not initialize an LLM or
spend GPU time; it only materializes files in ``uveitis-models``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import modal

from modal_volumes import (
    DECISION_SUBDIR,
    MODELS_VOLUME_NAME,
    QWEN_SUBDIR,
    QWEN4B_SUBDIR,
    models_volume,
)


APP_NAME = "uveitis-prepare-models"
HF_CACHE = "/models/.hf-cache"

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("huggingface_hub==0.34.4", "hf_transfer==0.1.9")
    .env(
        {
            "HF_HOME": HF_CACHE,
            "HF_HUB_CACHE": f"{HF_CACHE}/hub",
            "HF_HUB_ENABLE_HF_TRANSFER": "1",
        }
    )
    .add_local_file(
        Path(__file__).with_name("modal_volumes.py"),
        remote_path="/root/modal_volumes.py",
        copy=True,
    )
)

app = modal.App(APP_NAME)

MODELS = (
    ("Qwen/Qwen3.5-2B", QWEN_SUBDIR),
    ("Qwen/Qwen3.5-4B", QWEN4B_SUBDIR),
    ("internlm/Intern-Decision-4B", DECISION_SUBDIR),
)


def _snapshot(model_id: str, target: Path) -> dict[str, object]:
    from huggingface_hub import snapshot_download

    if target.is_dir() and any(target.iterdir()):
        return {
            "model": model_id,
            "status": "already_present",
            "target": str(target),
        }

    target.mkdir(parents=True, exist_ok=True)
    selected = snapshot_download(
        repo_id=model_id,
        local_dir=str(target),
        token=os.environ.get("HF_TOKEN") or None,
        resume_download=True,
    )
    files = [path for path in target.rglob("*") if path.is_file()]
    total_bytes = sum(path.stat().st_size for path in files)
    return {
        "model": model_id,
        "status": "downloaded",
        "target": str(target),
        "snapshot": selected,
        "files": len(files),
        "bytes": total_bytes,
    }


@app.function(
    image=image,
    volumes={"/models": models_volume},
    timeout=60 * 60,
)
def materialize_models() -> str:
    results = []
    try:
        for model_id, subdir in MODELS:
            results.append(_snapshot(model_id, Path("/models") / subdir))
        models_volume.commit()
    except BaseException as exc:
        results.append(
            {
                "status": "error",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        )
        models_volume.commit()
        raise
    return json.dumps(results, indent=2, ensure_ascii=False)


@app.function(volumes={"/models": models_volume})
def list_model_volume() -> str:
    files = []
    root = Path("/models")
    if root.exists():
        for path in sorted(root.rglob("*")):
            if path.is_file() and ".cache" not in path.parts:
                files.append(
                    {
                        "path": str(path.relative_to(root)),
                        "bytes": path.stat().st_size,
                    }
                )
    return json.dumps(
        {
            "volume": MODELS_VOLUME_NAME,
            "files": files,
            "total_files": len(files),
            "total_bytes": sum(item["bytes"] for item in files),
        },
        indent=2,
        ensure_ascii=False,
    )


@app.local_entrypoint()
def main() -> None:
    print(materialize_models.remote())
    print(list_model_volume.remote())

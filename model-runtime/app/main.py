from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_DIR = ROOT / "model-training" / "models" / "qwen" / "Qwen3.5-4B"
DEFAULT_ADAPTER_DIR = (
    ROOT
    / "model-training"
    / "assets"
    / "qwen3.5-4b"
    / "local-4060-oct-focus-cont-20261025-01"
    / "best_adapter"
)

app = FastAPI(
    title="Uveitis Model Runtime",
    version="0.1.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)


def _path_status(path: Path) -> str:
    return "ready" if path.is_dir() else "missing"


@app.get("/health")
def health() -> dict:
    model_dir = Path(os.environ.get("MODEL_RUNTIME_MODEL_DIR", DEFAULT_MODEL_DIR))
    adapter_dir = Path(os.environ.get("MODEL_RUNTIME_ADAPTER_DIR", DEFAULT_ADAPTER_DIR))
    model_ready = model_dir.is_dir()
    adapter_ready = (
        (adapter_dir / "adapter_config.json").is_file()
        and (adapter_dir / "adapter_model.safetensors").is_file()
    )
    return {
        "status": "ok" if model_ready and adapter_ready else "degraded",
        "service": "model-runtime",
        "gpu_required": True,
        "model": {
            "name": "Qwen3.5-4B",
            "path": str(model_dir),
            "status": _path_status(model_dir),
        },
        "adapter": {
            "path": str(adapter_dir),
            "status": "ready" if adapter_ready else "missing",
        },
        "decision_model": {
            "name": "Intern-Decision-4B",
            "status": "disabled",
        },
    }


@app.get("/v1/models")
def models() -> dict:
    payload = health()
    return {
        "models": [
            {
                "role": "qwen_judgment",
                "name": payload["model"]["name"],
                "status": payload["model"]["status"],
            },
            {
                "role": "adapter",
                "name": payload["adapter"]["path"],
                "status": payload["adapter"]["status"],
            },
            {
                "role": "decision",
                "name": payload["decision_model"]["name"],
                "status": payload["decision_model"]["status"],
            },
        ]
    }

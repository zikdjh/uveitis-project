from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field


LOG = logging.getLogger("uveitis.model_embedding")
logging.basicConfig(level=logging.INFO)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_PATH = ROOT / "models" / "bge-m3"
DEFAULT_MODEL_NAME = "BAAI/bge-m3"
DEFAULT_DIMENSION = 1024
MAX_INPUT_CHARS = 20_000
MAX_MODEL_NAME_CHARS = 128


class EmbeddingRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    input: str = Field(min_length=1, max_length=MAX_INPUT_CHARS)


class EmbeddingResponse(BaseModel):
    embedding: list[float]
    dimension: int
    model: str
    latency_ms: int
    generated_at: str


@dataclass(frozen=True)
class ServiceConfig:
    model_path: Path
    model_name: str
    dimension: int
    batch_size: int
    max_length: int


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}")
    return value


def _load_config() -> ServiceConfig:
    return ServiceConfig(
        model_path=Path(
            os.environ.get("EMBEDDING_MODEL_PATH", str(DEFAULT_MODEL_PATH))
        ).resolve(),
        model_name=os.environ.get("EMBEDDING_MODEL_NAME", DEFAULT_MODEL_NAME)[
            :MAX_MODEL_NAME_CHARS
        ],
        dimension=_env_int("EMBEDDING_DIMENSION", DEFAULT_DIMENSION, 8, 4096),
        batch_size=_env_int("EMBEDDING_BATCH_SIZE", 8, 1, 128),
        max_length=_env_int("EMBEDDING_MAX_LENGTH", 1024, 16, 8192),
    )


class BgeM3EmbeddingService:
    """Lazy-loading CPU wrapper around BGEM3FlagModel."""

    device = "cpu"

    def __init__(self, config: ServiceConfig) -> None:
        self.config = config
        self.model_path = config.model_path
        self._model: Any | None = None
        self._lock = threading.Lock()

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def model_ready(self) -> bool:
        return (self.model_path / "config.json").is_file()

    def _load(self):
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is not None:
                return self._model
            if not self.model_ready():
                raise FileNotFoundError(
                    f"BGE-M3 模型不存在: {self.model_path}。"
                    "请先执行 ModelScope 下载命令。"
                )
            import torch
            from FlagEmbedding import BGEM3FlagModel

            torch.set_num_threads(max(1, min(torch.get_num_threads(), 8)))
            self._model = BGEM3FlagModel(
                str(self.model_path),
                use_fp16=False,
                devices=[self.device],
            )
        return self._model

    def embed(self, text: str) -> list[float]:
        model = self._load()
        output = model.encode(
            [text],
            batch_size=self.config.batch_size,
            max_length=self.config.max_length,
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )
        vectors = output.get("dense_vecs")
        if vectors is None or len(vectors) != 1:
            raise ValueError("BGE-M3 未返回预期的 dense_vecs")
        vector = [float(value) for value in vectors[0]]
        if len(vector) != self.config.dimension:
            raise ValueError(
                f"BGE-M3 向量维度应为 {self.config.dimension}，实际为 {len(vector)}"
            )
        return vector


app = FastAPI(
    title="Uveitis Model Embedding",
    version="0.1.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)


_service: BgeM3EmbeddingService | None = None
_service_lock = threading.Lock()


def _get_service() -> BgeM3EmbeddingService:
    global _service
    if _service is not None:
        return _service
    with _service_lock:
        if _service is None:
            _service = BgeM3EmbeddingService(_load_config())
    return _service


@app.get("/health")
def health() -> dict:
    config = _load_config()
    service = _service
    ready = (config.model_path / "config.json").is_file()
    return {
        "status": "ok" if ready else "degraded",
        "service": "model/embedding",
        "model": {
            "name": config.model_name,
            "path": str(config.model_path),
            "status": "ready" if ready else "missing",
            "dimension": config.dimension,
            "device": "cpu",
        },
        "inference": {
            "endpoint": "/v1/embeddings",
            "status": "ready" if ready else "degraded",
            "loaded": bool(service and service.loaded),
            "internal_token_required": bool(
                os.environ.get("EMBEDDING_INTERNAL_TOKEN", "")
            ),
        },
    }


@app.post("/v1/embeddings", response_model=EmbeddingResponse)
def embeddings(payload: EmbeddingRequest, request: Request) -> EmbeddingResponse:
    internal_token = os.environ.get("EMBEDDING_INTERNAL_TOKEN", "")
    supplied_token = request.headers.get("X-Internal-Service-Token", "")
    if internal_token and supplied_token != internal_token:
        raise HTTPException(status_code=401, detail="Invalid internal service token")
    if not payload.input.strip():
        raise HTTPException(status_code=422, detail="input must not be blank")

    service = _get_service()
    started = time.perf_counter()
    try:
        vector = service.embed(payload.input)
    except FileNotFoundError as exc:
        LOG.error("embedding_model_missing: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Embedding model files are missing",
        ) from exc
    except Exception as exc:
        LOG.exception("embedding_failed")
        raise HTTPException(
            status_code=503,
            detail=f"Embedding inference unavailable: {type(exc).__name__}",
        ) from exc

    return EmbeddingResponse(
        embedding=vector,
        dimension=len(vector),
        model=service.config.model_name,
        latency_ms=int((time.perf_counter() - started) * 1000),
        generated_at=datetime.now(UTC).isoformat(),
    )

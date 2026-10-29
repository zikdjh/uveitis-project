import hashlib
import json
import math
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import uuid4

import httpx

from app.core.config import Settings
from app.schemas.case import (
    KnowledgeDocument,
    KnowledgeDocumentCreate,
    KnowledgeIndexStatus,
    KnowledgeMatch,
)


class EmbeddingProvider(Protocol):
    mode: str

    def embed(self, text: str) -> list[float]: ...


class HashingEmbeddingProvider:
    """Deterministic local vectors for transport and storage tests."""

    mode = "memory"

    def __init__(self, dimension: int) -> None:
        if dimension <= 0:
            raise ValueError("向量维度必须大于 0")
        self.dimension = dimension

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        terms = [term for term in text.lower().split() if term] or [text.lower()]
        for term in terms:
            digest = hashlib.blake2b(term.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "little") % self.dimension
            vector[bucket] += 1.0 if digest[4] & 1 else -1.0
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            vector[0] = 1.0
            return vector
        return [value / norm for value in vector]


class RemoteEmbeddingProvider:
    mode = "remote"

    def __init__(
        self, endpoint: str, timeout: float = 30.0, token: str = ""
    ) -> None:
        if not endpoint:
            raise ValueError("APP_RETRIEVAL_SERVICE_URL 未配置")
        # Match the perception client convention: the configured value is the
        # service base URL and the provider owns the endpoint path.
        self.endpoint = endpoint.rstrip("/") + "/v1/embeddings"
        self.timeout = timeout
        self.token = token
        self.headers = (
            {"X-Internal-Service-Token": token} if token else {}
        )

    def embed(self, text: str) -> list[float]:
        response = httpx.post(
            self.endpoint,
            json={"input": text},
            timeout=self.timeout,
            headers=self.headers,
        )
        response.raise_for_status()
        payload = response.json()
        vector = payload.get("embedding") or payload.get("vector")
        if vector is None and isinstance(payload.get("data"), list):
            item = payload["data"][0] if payload["data"] else {}
            vector = item.get("embedding") if isinstance(item, dict) else None
        if not isinstance(vector, list) or not vector:
            raise ValueError("向量服务响应缺少 embedding")
        return [float(value) for value in vector]


class ZvecKnowledgeRepository:
    """Persists knowledge metadata in Zvec and audit fields beside it."""

    def __init__(self, path: Path, collection: str, dimension: int) -> None:
        self.path = path / collection
        self.dimension = dimension
        self.metadata_path = path / f"{collection}.metadata.json"
        self._collection = None
        self._metadata: dict[str, dict] | None = None
        self._lock = threading.RLock()

    def _open(self):
        with self._lock:
            if self._collection is not None:
                return self._collection
            import zvec

            self.path.parent.mkdir(parents=True, exist_ok=True)
            if not self.path.exists():
                schema = zvec.CollectionSchema(
                    name=self.path.name,
                    fields=[
                        zvec.FieldSchema(name="title", data_type=zvec.DataType.STRING),
                        zvec.FieldSchema(name="content", data_type=zvec.DataType.STRING),
                        zvec.FieldSchema(name="source", data_type=zvec.DataType.STRING),
                        zvec.FieldSchema(name="category", data_type=zvec.DataType.STRING),
                        zvec.FieldSchema(
                            name="created_at", data_type=zvec.DataType.STRING
                        ),
                    ],
                    vectors=zvec.VectorSchema(
                        name="embedding",
                        data_type=zvec.DataType.VECTOR_FP32,
                        dimension=self.dimension,
                        index_param=zvec.HnswIndexParam(
                            metric_type=zvec.MetricType.COSINE
                        ),
                    ),
                )
                self._collection = zvec.create_and_open(
                    path=str(self.path), schema=schema
                )
            else:
                self._collection = zvec.open(str(self.path))
            return self._collection

    def _load_metadata(self) -> dict[str, dict]:
        if self._metadata is None:
            if self.metadata_path.exists():
                self._metadata = json.loads(
                    self.metadata_path.read_text(encoding="utf-8")
                )
            else:
                self._metadata = {}
        return self._metadata

    def _save_metadata(self) -> None:
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.metadata_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(self._metadata or {}, ensure_ascii=False),
            encoding="utf-8",
        )
        temporary.replace(self.metadata_path)

    def upsert(self, document: KnowledgeDocument, vector: list[float]) -> None:
        import zvec

        self._validate_vector(vector)
        with self._lock:
            collection = self._open()
            status = collection.upsert(
                zvec.Doc(
                    id=document.id,
                    vectors={"embedding": vector},
                    fields={
                        "title": document.title,
                        "content": document.content,
                        "source": document.source,
                        "category": document.category,
                        "created_at": document.created_at.isoformat(),
                    },
                )
            )
            _raise_for_status(status, "写入知识文档失败")
            collection.flush()
            metadata = self._load_metadata()
            metadata[document.id] = document.model_dump(mode="json")
            self._save_metadata()

    def search(
        self, vector: list[float], top_k: int, category: str | None = None
    ) -> list[KnowledgeMatch]:
        import zvec

        self._validate_vector(vector)
        with self._lock:
            if not self.path.exists():
                return []
            collection = self._open()
            results = collection.query(
                queries=zvec.Query(field_name="embedding", vector=vector),
                topk=top_k,
                filter=f"category = '{category}'" if category else None,
                output_fields=["title", "content", "source", "category", "created_at"],
            )
            metadata = self._load_metadata()
            matches: list[KnowledgeMatch] = []
            for result in results:
                raw = metadata.get(result.id)
                if raw is None:
                    continue
                # Zvec COSINE returns distance: 0 is an exact match.
                score = max(0.0, min(1.0, 1.0 - float(result.score)))
                matches.append(
                    KnowledgeMatch(
                        document=KnowledgeDocument.model_validate(raw),
                        score=score,
                    )
                )
            return matches

    def count(self) -> int:
        with self._lock:
            if not self.path.exists() or not self.metadata_path.exists():
                return 0
            return len(self._load_metadata())

    def exists(self) -> bool:
        return self.path.exists()

    def close(self) -> None:
        with self._lock:
            if self._collection is not None:
                self._collection.close()
                self._collection = None

    def _validate_vector(self, vector: list[float]) -> None:
        if len(vector) != self.dimension:
            raise ValueError(
                f"向量维度应为 {self.dimension}，实际为 {len(vector)}"
            )


def _raise_for_status(status, message: str) -> None:
    if not status.ok():
        detail = status.message() if callable(status.message) else status.message
        detail = detail or str(status)
        raise RuntimeError(f"{message}: {detail}")


class KnowledgeStore:
    def __init__(self, settings: Settings, path: Path) -> None:
        self.settings = settings
        self.repository = ZvecKnowledgeRepository(
            path,
            settings.vector_collection_name,
            settings.vector_dimension,
        )
        if settings.vector_provider == "remote":
            self.embedding = RemoteEmbeddingProvider(
                settings.retrieval_service_url,
                token=settings.internal_service_token,
            )
        else:
            self.embedding = HashingEmbeddingProvider(settings.vector_dimension)

    def add(
        self, payload: KnowledgeDocumentCreate, vector: list[float] | None = None
    ) -> KnowledgeDocument:
        document = KnowledgeDocument(
            id=str(uuid4()),
            title=payload.title,
            content=payload.content,
            source=payload.source,
            category=payload.category,
            created_at=datetime.now(UTC),
        )
        embedding = vector or payload.vector or self.embedding.embed(
            f"{payload.title} {payload.content}"
        )
        self.repository.upsert(document, embedding)
        return document

    def search(
        self,
        query: str,
        vector: list[float] | None,
        top_k: int,
        category: str | None = None,
    ) -> list[KnowledgeMatch]:
        embedding = vector or self.embedding.embed(query)
        return self.repository.search(embedding, top_k, category)

    def status(self) -> KnowledgeIndexStatus:
        return KnowledgeIndexStatus(
            collection=self.settings.vector_collection_name,
            path=str(self.repository.path),
            documents=self.repository.count(),
            dimension=self.settings.vector_dimension,
            embedding_mode=self.settings.vector_provider,
            ready=self.repository.exists(),
        )

from __future__ import annotations

from pathlib import Path

import app.main as main
from fastapi.testclient import TestClient


class FakeBgeModel:
    def encode(self, texts, **kwargs):
        return {"dense_vecs": [[0.25, -0.75] for _ in texts]}


class FakeService:
    device = "cpu"

    def __init__(self, *, fail: bool = False) -> None:
        self.config = main._load_config()
        self.model_path = self.config.model_path
        self.fail = fail
        self._loaded = True

    @property
    def loaded(self) -> bool:
        return self._loaded

    def embed(self, text: str) -> list[float]:
        if self.fail:
            raise FileNotFoundError("fake missing model")
        return [0.25, -0.75]


def test_health_reports_model_status(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_MODEL_PATH", str(tmp_path))
    client = TestClient(main.app)

    degraded = client.get("/health").json()
    assert degraded["status"] == "degraded"
    assert degraded["model"]["status"] == "missing"

    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    ready = client.get("/health").json()
    assert ready["status"] == "ok"
    assert ready["inference"]["endpoint"] == "/v1/embeddings"


def test_embeddings_requires_internal_token(monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_INTERNAL_TOKEN", "secret")
    monkeypatch.setattr(main, "_service", FakeService())
    client = TestClient(main.app)

    denied = client.post("/v1/embeddings", json={"input": "葡萄膜炎"})
    assert denied.status_code == 401

    allowed = client.post(
        "/v1/embeddings",
        json={"input": "葡萄膜炎"},
        headers={"X-Internal-Service-Token": "secret"},
    )
    assert allowed.status_code == 200
    payload = allowed.json()
    assert payload["embedding"] == [0.25, -0.75]
    assert payload["dimension"] == 2


def test_embeddings_rejects_blank_input(monkeypatch) -> None:
    monkeypatch.setattr(main, "_service", FakeService())
    client = TestClient(main.app)

    response = client.post("/v1/embeddings", json={"input": "   "})
    assert response.status_code == 422


def test_embeddings_reports_missing_model(monkeypatch) -> None:
    monkeypatch.setattr(main, "_service", FakeService(fail=True))
    client = TestClient(main.app)

    response = client.post("/v1/embeddings", json={"input": "葡萄膜炎"})
    assert response.status_code == 503

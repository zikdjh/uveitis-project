from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import main


TEST_ROOT = Path(__file__).resolve().parents[1] / ".test-tmp"


@pytest.fixture
def case_root() -> Path:
    root = TEST_ROOT / uuid4().hex
    root.mkdir(parents=True)
    return root


@pytest.fixture
def image_root(case_root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = case_root / "images"
    root.mkdir()
    Image.new("RGB", (32, 24), (18, 90, 110)).save(root / "img-1.png")
    monkeypatch.setenv("MODEL_RUNTIME_IMAGE_ROOT", str(root))
    monkeypatch.delenv("MODEL_RUNTIME_UPLOAD_ROOT", raising=False)
    monkeypatch.delenv("MODEL_RUNTIME_INTERNAL_TOKEN", raising=False)
    return root


class FakeRuntime:
    def __init__(self, model_dir: Path) -> None:
        self.model_dir = model_dir
        self.loaded = False
        self._adapter_sha256 = "test-adapter-hash"
        self.calls: list[tuple[str, list[Path]]] = []
        self.failure: Exception | None = None

    def load(self) -> None:
        self.loaded = True

    def peak_memory(self) -> tuple[float | None, float | None]:
        return 3.5, 3.7

    def judge(self, task: str, image_paths: list[Path]):
        self.calls.append((task, image_paths))
        if self.failure:
            raise self.failure
        return (
            {
                "label": "CNV",
                "confidence": 0.82,
                "impression": "可见黄斑区异常信号",
                "findings": [
                    {
                        "label": "macular abnormality",
                        "location": "macula",
                        "confidence": 0.78,
                    }
                ],
                "recommendations": [],
                "requires_human_review": True,
            },
            False,
        )


@pytest.fixture
def client(image_root: Path, monkeypatch: pytest.MonkeyPatch):
    runtime = FakeRuntime(Path("Qwen3.5-4B"))
    monkeypatch.setattr(main, "_runtime", runtime)
    return TestClient(main.app), runtime


def payload(local_path: Path | None = None) -> dict:
    image = {"id": "img-1", "kind": "oct"}
    if local_path is not None:
        image["local_path"] = str(local_path)
    return {
        "task": "oct_aux_4class",
        "case": {
            "case_id": "case-1",
            "patient_age": 42,
            "complaint": "视力下降",
            "images": [image],
        },
        "output_schema": {"label": "string"},
        "constraints": ["Return compact JSON only."],
    }


def test_judge_returns_stable_structured_result(client, image_root: Path) -> None:
    api, runtime = client
    response = api.post("/v1/judge", json=payload(image_root / "img-1.png"))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["result"]["label"] == "CNV"
    assert body["result"]["requires_human_review"] is True
    assert body["research_use_only"] is True
    assert body["adapter_sha256"] == "test-adapter-hash"
    assert body["truncated"] is False
    assert runtime.calls[0][0] == "oct_aux_4class"
    assert runtime.calls[0][1] == [(image_root / "img-1.png").resolve()]


def test_judge_rejects_image_outside_allowed_roots(
    client,
    case_root: Path,
) -> None:
    api, runtime = client
    outside = case_root / "outside.png"
    Image.new("RGB", (8, 8)).save(outside)

    response = api.post("/v1/judge", json=payload(outside))

    assert response.status_code == 403
    assert runtime.calls == []


def test_judge_requires_images(client) -> None:
    api, runtime = client
    body = payload()
    body["case"]["images"] = []

    response = api.post("/v1/judge", json=body)

    assert response.status_code == 422
    assert runtime.loaded is False


def test_judge_rejects_unsupported_task(client) -> None:
    api, runtime = client
    body = payload()
    body["task"] = "unapproved_task"

    response = api.post("/v1/judge", json=body)

    assert response.status_code == 422
    assert runtime.loaded is False


def test_judge_reports_busy_runtime_and_invalid_model_response(client) -> None:
    api, runtime = client
    runtime.failure = TimeoutError("Runtime is busy")
    busy = api.post("/v1/judge", json=payload())
    assert busy.status_code == 503
    assert "busy" in busy.json()["detail"]

    runtime.failure = ValueError("Model did not return an allowed structured label")
    invalid = api.post("/v1/judge", json=payload())
    assert invalid.status_code == 422


def test_parse_result_rejects_non_allowed_label() -> None:
    with pytest.raises(ValueError, match="allowed structured label"):
        main._parse_result('{"label":"not-a-label"}', "oct_aux_4class")


def test_parse_result_uses_validated_fallback_finding() -> None:
    result = main._parse_result(
        '```json\\n{"label":"CNV","confidence":2}\\n```',
        "oct_aux_4class",
    )
    assert result["confidence"] == 1.0
    assert result["findings"] == [
        {"label": "CNV", "location": "", "confidence": 1.0}
    ]


def test_image_loader_keeps_original_size_for_processor(
    case_root: Path,
) -> None:
    image_path = case_root / "large.png"
    Image.new("RGB", (512, 384), (10, 40, 90)).save(image_path)

    image = main._load_rgb_image(image_path, max_decoded_pixels=1_000_000)

    assert image.size == (512, 384)
    image.close()


def test_image_loader_rejects_oversized_decode(case_root: Path) -> None:
    image_path = case_root / "oversized.png"
    Image.new("RGB", (100, 100), (10, 40, 90)).save(image_path)

    with pytest.raises(ValueError, match="Decoded image is too large"):
        main._load_rgb_image(image_path, max_decoded_pixels=9_999)


def test_runtime_uses_configured_busy_timeout(
    case_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = main.QwenRuntime(
        case_root / "model",
        case_root / "adapter",
        image_pixels=65_536,
        max_new_tokens=32,
        inference_wait_seconds=7,
    )
    waits: list[int] = []

    class BusyLock:
        def acquire(self, *, timeout: int) -> bool:
            waits.append(timeout)
            return False

        def release(self) -> None:
            raise AssertionError("A lock that was not acquired must not be released")

    runtime._inference_lock = BusyLock()

    with pytest.raises(TimeoutError, match="Runtime is busy"):
        runtime.judge("oct_aux_4class", [case_root / "image.png"])

    assert waits == [7]

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

from app.core.config import Settings
from app.schemas.case import CaseImage, CaseRead
from app.services.integrations import OptionalIntegrations


def _case(upload_dir: Path) -> CaseRead:
    case_dir = upload_dir / "case-contract"
    case_dir.mkdir(parents=True)
    (case_dir / "image-1.png").write_bytes(b"fixture")
    now = datetime.now(UTC)
    return CaseRead(
        id="case-contract",
        patient_age=48,
        patient_sex="F",
        complaint="左眼视物模糊",
        medical_history="",
        affected_eye="OS",
        consent_confirmed=True,
        status="created",
        created_at=now,
        updated_at=now,
        images=[
            CaseImage(
                id="image-1",
                kind="oct",
                filename="image-1.png",
                content_type="image/png",
                size_bytes=7,
                url="/uploads/case-contract/image-1.png",
            )
        ],
    )


def test_qwen_runtime_contract_sends_task_and_reads_nested_result(
    tmp_path: Path,
) -> None:
    received: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/judge"
        body = json.loads(request.content)
        received.append(body)
        return httpx.Response(
            200,
            json={
                "result": {
                    "label": "CNV",
                    "confidence": 0.83,
                    "impression": "黄斑区可见异常信号",
                    "findings": [],
                    "requires_human_review": True,
                }
            },
        )

    integrations = OptionalIntegrations(
        Settings(
            model_mode="remote",
            qwen_judgment_enabled=True,
            perception_service_url="http://runtime.test",
            integration_timeout_seconds=45,
            data_dir=tmp_path,
        ),
        client_factory=lambda **kwargs: httpx.Client(
            transport=httpx.MockTransport(handler),
            **kwargs,
        ),
    )

    result = integrations.qwen_judgment(_case(tmp_path / "uploads"))

    assert result.status == "completed", result.detail
    assert result.data["label"] == "CNV"
    assert result.data["findings"][0]["label"] == "CNV"
    assert received[0]["task"] == "oct_aux_4class"
    assert received[0]["case"]["images"][0]["local_path"].endswith(
        "image-1.png"
    )


def test_qwen_runtime_failure_does_not_raise(tmp_path: Path) -> None:
    integrations = OptionalIntegrations(
        Settings(
            model_mode="remote",
            qwen_judgment_enabled=True,
            perception_service_url="http://runtime.test",
            data_dir=tmp_path,
        ),
        client_factory=lambda **kwargs: httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(503, json={"detail": "busy"})
            ),
            **kwargs,
        ),
    )

    result = integrations.qwen_judgment(_case(tmp_path / "uploads"))

    assert result.status == "failed"
    assert "不可用" in result.detail

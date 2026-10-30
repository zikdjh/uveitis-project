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
        owner_id="doctor-1",
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
                },
                "model": "Qwen3.5-4B",
                "adapter_sha256": "a" * 64,
                "latency_ms": 2400,
                "generated_at": "2026-10-27T10:00:00+00:00",
                "truncated": False,
                "peak_allocated_gib": 3.27,
                "peak_reserved_gib": 3.36,
                "research_use_only": True,
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
    assert received[0]["enable_thinking"] is False
    assert received[0]["case"]["images"][0]["local_path"].endswith(
        "image-1.png"
    )
    assert received[0]["case"]["owner_id"] == "doctor-1"
    runtime = result.data["runtime"]
    assert runtime["model"] == "Qwen3.5-4B"
    assert runtime["adapter_sha256"] == "a" * 64
    assert runtime["latency_ms"] == 2400
    assert runtime["truncated"] is False
    assert runtime["peak_reserved_gib"] == 3.36


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


def test_qwen_runtime_tool_call_loop_runs_web_search(tmp_path: Path) -> None:
    judge_calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "runtime.test":
            body = json.loads(request.content)
            judge_calls.append(body)
            if len(judge_calls) == 1:
                assert body["tools"] == ["web_search"]
                assert body["tool_results"] == []
                return httpx.Response(
                    200,
                    json={
                        "status": "tool_call",
                        "tool_call": {
                            "tool": "web_search",
                            "arguments": {"query": "uveitis guideline"},
                        },
                        "thinking": "需要检索证据",
                        "model": "Qwen3.5-4B",
                        "latency_ms": 120,
                        "truncated": False,
                    },
                )
            assert body["tool_results"], "second round must carry search results"
            return httpx.Response(
                200,
                json={
                    "result": {
                        "label": "CNV",
                        "confidence": 0.8,
                        "impression": "黄斑区异常信号",
                        "findings": [],
                        "requires_human_review": True,
                    },
                    "model": "Qwen3.5-4B",
                    "latency_ms": 200,
                    "truncated": False,
                    "thinking": "已结合检索证据完成判断",
                },
            )
        if request.url.host == "api.bochaai.com":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "webPages": {
                            "value": [
                                {
                                    "name": "Guideline",
                                    "url": "https://source.test/guideline",
                                    "summary": "s",
                                }
                            ]
                        }
                    }
                },
            )
        return httpx.Response(404)

    integrations = OptionalIntegrations(
        Settings(
            model_mode="remote",
            qwen_judgment_enabled=True,
            perception_service_url="http://runtime.test",
            web_search_enabled=True,
            web_search_providers="bocha",
            bocha_api_key="bocha-key",
            data_dir=tmp_path,
        ),
        client_factory=lambda **kwargs: httpx.Client(
            transport=httpx.MockTransport(handler),
            **kwargs,
        ),
    )

    result = integrations.qwen_judgment(_case(tmp_path / "uploads"))

    assert result.status == "completed", result.detail
    assert len(judge_calls) == 2
    tool_result = judge_calls[1]["tool_results"][0]
    assert tool_result["query"] == "uveitis guideline"
    assert tool_result["results"][0]["url"] == "https://source.test/guideline"
    assert result.data["web_evidence"][0].url == "https://source.test/guideline"
    runtime = result.data["runtime"]
    assert runtime["tool_rounds"] == 1
    assert runtime["searched_queries"] == ["uveitis guideline"]
    assert "已结合检索证据" in runtime["thinking"]

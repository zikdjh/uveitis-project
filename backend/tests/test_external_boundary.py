"""Images and case records must never reach a third-party API."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest

from app.core.config import Settings
from app.schemas.case import CaseImage, CaseRead
from app.core.external_boundary import (
    assert_external_payload,
    assert_external_text,
    find_external_violations,
    sanitize_external_payload,
)
from app.services.integrations import OptionalIntegrations


COMPLAINT = "左眼视物模糊三天伴眼前黑影飘动"
HISTORY = "既往确诊强直性脊柱炎十年"


def make_case() -> CaseRead:
    now = datetime.now(UTC)
    return CaseRead(
        id="case-privacy-001",
        patient_age=42,
        patient_sex="F",
        complaint=COMPLAINT,
        medical_history=HISTORY,
        affected_eye="OS",
        consent_confirmed=True,
        status="created",
        created_at=now,
        updated_at=now,
    )


def test_sanitize_drops_case_image_and_inline_binary_data() -> None:
    cleaned = sanitize_external_payload(
        {
            "judgment": {"label": "cnv", "case_id": "case-1"},
            "images": [{"local_path": "data/uploads/a.png"}],
            "complaint": COMPLAINT,
            "payload": "data:image/png;base64,AAAA",
            "rag_evidence": [{"source": "guideline", "snippet": "text"}],
        }
    )

    assert cleaned == {
        "judgment": {"label": "cnv"},
        "payload": "[redacted-外部接口不接收病例或影像数据]",
        "rag_evidence": [{"source": "guideline", "snippet": "text"}],
    }
    assert find_external_violations(cleaned) == []


def test_assert_external_payload_refuses_case_and_image_fields() -> None:
    with pytest.raises(ValueError) as case_error:
        assert_external_payload(
            {"nested": {"medical_history": HISTORY}},
            service="外部总结",
        )
    assert "medical_history" in str(case_error.value)

    with pytest.raises(ValueError) as image_error:
        assert_external_payload(
            {"images": [{"local_path": "a.png"}]},
            service="外部总结",
        )
    assert "images" in str(image_error.value)


def test_assert_external_text_refuses_verbatim_case_fields() -> None:
    assert assert_external_text("cnv macular abnormality", make_case(), service="网络搜索")

    with pytest.raises(ValueError):
        assert_external_text(f"query {COMPLAINT}", make_case(), service="网络搜索")

    with pytest.raises(ValueError):
        assert_external_text(f"summary: {HISTORY}", make_case(), service="外部总结")


def summary_handler(recorded: list[dict]) -> object:
    def handler(request: httpx.Request) -> httpx.Response:
        recorded.append(json.loads(request.content.decode("utf-8")))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "summary": "已汇总当前证据。",
                                    "recommendations": [],
                                    "uncertainties": [],
                                    "evidence_ids": [],
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            },
        )

    return handler


def test_external_summary_never_receives_case_fields_or_images() -> None:
    recorded: list[dict] = []
    settings = Settings(
        model_mode="remote",
        external_summary_enabled=True,
        external_summary_base_url="http://summary.local/v1",
        external_summary_api_key="summary-key",
        external_summary_model="summary-model",
    )
    integrations = OptionalIntegrations(
        settings,
        client_factory=lambda **kwargs: httpx.Client(
            transport=httpx.MockTransport(summary_handler(recorded)), **kwargs
        ),
    )
    case = make_case()
    case.images = [
        CaseImage(
            id="img-1",
            filename="oct.png",
            kind="oct",
            content_type="image/png",
            size_bytes=1024,
            url="/api/v1/cases/case-privacy-001/images/img-1",
        )
    ]

    result = integrations.external_summary(
        case,
        {"label": "cnv", "impression": "黄斑区可疑异常"},
        {},
        [],
        [],
    )

    assert result.status == "completed"
    assert len(recorded) == 1
    body = recorded[0]
    serialized = json.dumps(body, ensure_ascii=False)
    assert COMPLAINT not in serialized
    assert HISTORY not in serialized
    assert case.id not in serialized
    assert "oct.png" not in serialized
    assert "clinical_context" not in body
    assert find_external_violations(body) == []
    # Model output and retrieved evidence are still allowed to be summarized.
    assert "cnv" in serialized


def test_external_summary_drops_untrusted_free_text_from_model_outputs() -> None:
    recorded: list[dict] = []
    settings = Settings(
        model_mode="remote",
        external_summary_enabled=True,
        external_summary_base_url="http://summary.local/v1",
        external_summary_api_key="summary-key",
        external_summary_model="summary-model",
    )
    integrations = OptionalIntegrations(
        settings,
        client_factory=lambda **kwargs: httpx.Client(
            transport=httpx.MockTransport(summary_handler(recorded)), **kwargs
        ),
    )

    result = integrations.external_summary(
        make_case(),
        {
            "label": "cnv",
            "impression": f"主诉为：{COMPLAINT}",
            "patient_age": 42,
        },
        {
            "primary_class": "cnv",
            "impression": f"病史：{HISTORY}",
            "case": {"complaint": COMPLAINT},
        },
        [],
        [],
    )

    assert result.status == "completed"
    assert len(recorded) == 1
    serialized = json.dumps(recorded[0], ensure_ascii=False)
    assert COMPLAINT not in serialized
    assert HISTORY not in serialized
    assert "patient_age" not in serialized
    assert find_external_violations(recorded[0]) == []


def test_external_summary_refuses_a_model_label_that_quotes_case_text() -> None:
    recorded: list[dict] = []
    settings = Settings(
        model_mode="remote",
        external_summary_enabled=True,
        external_summary_base_url="http://summary.local/v1",
        external_summary_api_key="summary-key",
        external_summary_model="summary-model",
    )
    integrations = OptionalIntegrations(
        settings,
        client_factory=lambda **kwargs: httpx.Client(
            transport=httpx.MockTransport(summary_handler(recorded)), **kwargs
        ),
    )

    result = integrations.external_summary(
        make_case(),
        {"label": COMPLAINT, "confidence": 0.8},
        {},
        [],
        [],
    )

    assert result.status == "failed"
    assert "病例字段" in result.detail
    assert recorded == []


def test_web_search_query_never_contains_case_text() -> None:
    recorded: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        recorded.append(json.loads(request.content.decode("utf-8")))
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Uveitis guideline",
                        "url": "https://example.test/guideline",
                        "content": "Clinical evidence",
                    }
                ]
            },
        )

    settings = Settings(
        model_mode="remote",
        web_search_enabled=True,
        web_search_providers="tavily",
        tavily_api_key="search-key",
        web_search_max_results=3,
    )
    integrations = OptionalIntegrations(
        settings,
        client_factory=lambda **kwargs: httpx.Client(
            transport=httpx.MockTransport(handler), **kwargs
        ),
    )

    result = integrations.web_search(
        make_case(),
        {"label": "cnv", "findings": [{"label": "macular abnormality"}]},
        {},
    )

    assert result.status == "completed"
    assert len(recorded) == 1
    body = recorded[0]
    query = body["query"]
    assert COMPLAINT not in query
    assert HISTORY not in query
    assert "cnv" in query
    assert find_external_violations(body) == []


def test_web_search_falls_back_to_generic_query_without_model_labels() -> None:
    recorded: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        recorded.append(json.loads(request.content.decode("utf-8")))
        return httpx.Response(
            200,
            json={
                "results": [
                    {"title": "t", "url": "https://example.test/a", "content": "c"}
                ]
            },
        )

    settings = Settings(
        model_mode="remote",
        web_search_enabled=True,
        web_search_providers="tavily",
        tavily_api_key="search-key",
    )
    integrations = OptionalIntegrations(
        settings,
        client_factory=lambda **kwargs: httpx.Client(
            transport=httpx.MockTransport(handler), **kwargs
        ),
    )

    integrations.web_search(make_case(), {}, {})

    query = recorded[0]["query"]
    assert COMPLAINT not in query
    assert query.startswith("uveitis differential diagnosis")


def test_web_search_blocks_a_model_label_that_quotes_case_text() -> None:
    recorded: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        recorded.append(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json={"results": []})

    settings = Settings(
        model_mode="remote",
        web_search_enabled=True,
        web_search_providers="tavily",
        tavily_api_key="search-key",
    )
    integrations = OptionalIntegrations(
        settings,
        client_factory=lambda **kwargs: httpx.Client(
            transport=httpx.MockTransport(handler), **kwargs
        ),
    )

    result = integrations.web_search(
        make_case(),
        {"label": COMPLAINT, "findings": []},
        {},
    )

    assert result.status == "failed"
    assert "已阻止外发" in result.detail
    assert recorded == []

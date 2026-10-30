from datetime import UTC, datetime
import json

import httpx
import pytest

from app.core.config import Settings
from app.schemas.case import CaseRead
from app.schemas.integrations import IntegrationConfigUpdate as IntegrationUpdate
from app.services.integrations import OptionalIntegrations
from app.services.integration_settings import MemoryIntegrationSettingsStore, SecretBox


def make_case() -> CaseRead:
    now = datetime.now(UTC)
    return CaseRead(
        id="case-1",
        owner_id="doctor-1",
        patient_age=42,
        patient_sex="F",
        complaint="左眼视物模糊三天",
        medical_history="无特殊",
        affected_eye="OS",
        consent_confirmed=True,
        status="created",
        created_at=now,
        updated_at=now,
    )


def test_optional_integrations_normalize_qwen_search_and_summary() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "qwen.local":
            return httpx.Response(
                200,
                json={
                    "label": "cnv",
                    "confidence": 0.86,
                    "impression": "黄斑区可疑异常",
                    "findings": [
                        {
                            "label": "macular abnormality",
                            "location": "macula",
                            "confidence": 0.81,
                        }
                    ],
                },
            )
        if request.url.host == "api.tavily.com":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "title": "Uveitis guideline",
                            "url": "https://example.test/guideline",
                            "content": "Clinical evidence",
                            "score": 0.9,
                        }
                    ]
                },
            )
        if request.url.host == "summary.local":
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": (
                                    '{"summary":"已汇总当前证据。",'
                                    '"recommendations":["结合原始资料复核"],'
                                    '"uncertainties":[],"evidence_ids":[]}'
                                )
                            }
                        }
                    ]
                },
            )
        return httpx.Response(404, json={"error": "unexpected"})

    settings = Settings(
        model_mode="remote",
        qwen_judgment_enabled=True,
        perception_service_url="http://qwen.local",
        web_search_enabled=True,
        web_search_providers="tavily",
        tavily_api_key="test-key",
        external_summary_enabled=True,
        external_summary_base_url="http://summary.local/v1",
        external_summary_api_key="summary-key",
        external_summary_model="summary-model",
    )

    def client_factory(**kwargs) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler), **kwargs)

    integrations = OptionalIntegrations(settings, client_factory=client_factory)
    judgment = integrations.qwen_judgment(make_case())
    assert judgment.status == "completed"
    assert judgment.data["label"] == "cnv"
    assert judgment.data["findings"][0]["location"] == "macula"

    search = integrations.web_search(make_case(), judgment.data, {})
    assert search.status == "completed"
    assert search.data["results"][0].provider == "tavily"

    summary = integrations.external_summary(
        make_case(),
        judgment.data,
        {},
        [],
        search.data["results"],
    )
    assert summary.status == "completed"
    assert summary.data["summary"] == "已汇总当前证据。"
    assert summary.data["recommendations"] == ["结合原始资料复核"]


def test_optional_search_failure_is_reported_without_raising() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "unavailable"})

    settings = Settings(
        model_mode="remote",
        web_search_enabled=True,
        web_search_providers="tavily",
        tavily_api_key="test-key",
    )
    integrations = OptionalIntegrations(
        settings,
        client_factory=lambda **kwargs: httpx.Client(
            transport=httpx.MockTransport(handler),
            **kwargs,
        ),
    )
    result = integrations.web_search(make_case(), {}, {})
    assert result.status == "failed"
    assert "网络搜索失败" in result.detail


def _store() -> MemoryIntegrationSettingsStore:
    return MemoryIntegrationSettingsStore(
        SecretBox("test-integration-master-key-at-least-32-characters"),
    )


def test_summary_protocol_adapters(tmp_path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = json.loads(request.content)
        if request.url.path.endswith("/responses"):
            assert body["instructions"]
            return httpx.Response(
                200,
                json={
                    "output": [
                        {
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": json.dumps(
                                        {
                                            "summary": "Responses 汇总",
                                            "recommendations": ["复核原始影像"],
                                            "uncertainties": [],
                                            "evidence_ids": [],
                                        },
                                        ensure_ascii=False,
                                    ),
                                }
                            ]
                        }
                    ]
                },
            )
        if request.url.path.endswith("/messages"):
            assert request.headers["x-api-key"] == "anthropic-key"
            return httpx.Response(
                200,
                json={"content": [{"type": "text", "text": "{\"summary\": \"Anthropic 汇总\"}"}]},
            )
        assert body["messages"][0]["role"] == "system"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "{\"summary\": \"Chat 汇总\"}"
                        }
                    }
                ]
            },
        )

    settings = Settings(model_mode="remote")

    for protocol, base_url, key in (
        ("openai_responses", "https://summary.local/v1", "openai-key"),
        (
            "openai_chat_completions",
            "https://summary.local/v1",
            "chat-key",
        ),
        ("anthropic_messages", "https://summary.local/v1", "anthropic-key"),
    ):
        store = _store()
        store.update(
            IntegrationUpdate(
                summary_enabled=True,
                summary_protocol=protocol,
                summary_base_url=base_url,
                summary_model="test-model",
                summary_api_key=key,
            ),
            actor_id="admin",
        )
        integrations = OptionalIntegrations(
            settings,
            config_store=store,
            client_factory=lambda **kwargs: httpx.Client(
                transport=httpx.MockTransport(handler), **kwargs
            ),
        )
        result = integrations.external_summary(make_case(), {}, {}, [], [])
        assert result.status == "completed", result.detail
        assert result.data["summary"].endswith("汇总")

    assert len(requests) == 3
    assert requests[0].headers["authorization"] == "Bearer openai-key"
    assert requests[2].headers["anthropic-version"] == "2023-06-01"


def test_truncated_summary_keeps_only_complete_summary_text() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"summary":"截断前的摘要",'
                                '"recommendations":["复核'
                            )
                        }
                    }
                ]
            },
        )

    store = _store()
    store.update(
        IntegrationUpdate(
            summary_enabled=True,
            summary_protocol="openai_chat_completions",
            summary_base_url="https://summary.local/v1",
            summary_model="test-model",
            summary_api_key="chat-key",
        ),
        actor_id="admin",
    )
    integrations = OptionalIntegrations(
        Settings(model_mode="remote"),
        config_store=store,
        client_factory=lambda **kwargs: httpx.Client(
            transport=httpx.MockTransport(handler), **kwargs
        ),
    )

    result = integrations.external_summary(make_case(), {}, {}, [], [])

    assert result.status == "completed"
    assert result.data["summary"] == "截断前的摘要"
    assert result.data["recommendations"] == []


def test_summary_connection_probe_uses_selected_protocol() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/responses"):
            return httpx.Response(200, json={"output_text": "OK"})
        if request.url.path.endswith("/messages"):
            return httpx.Response(200, json={"content": [{"type": "text", "text": "OK"}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})

    settings = Settings(model_mode="remote")
    for protocol, base_url in (
        ("openai_responses", "https://summary.local/v1"),
        ("openai_chat_completions", "https://summary.local/v1"),
        ("anthropic_messages", "https://summary.local/v1"),
    ):
        store = _store()
        store.update(
            IntegrationUpdate(
                summary_enabled=True,
                summary_protocol=protocol,
                summary_base_url=base_url,
                summary_model="probe-model",
                summary_api_key="probe-key",
            ),
            actor_id="admin",
        )
        integrations = OptionalIntegrations(
            settings,
            config_store=store,
            client_factory=lambda **kwargs: httpx.Client(
                transport=httpx.MockTransport(handler), **kwargs
            ),
        )
        result = integrations.test_summary()
        assert result.ok is True, result.detail
        assert result.detail == "连接成功，模型 probe-model 已返回响应"
        assert result.attempts == 1
    assert len(requests) == 3
    assert requests[0].url.path.endswith("/responses")
    assert requests[1].url.path.endswith("/chat/completions")
    assert requests[2].url.path.endswith("/messages")


def test_summary_connection_probe_reports_unreachable_service() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(503, json={"error": "unavailable"})

    store = _store()
    store.update(
        IntegrationUpdate(
            summary_enabled=True,
            summary_protocol="openai_chat_completions",
            summary_base_url="https://summary.local/v1",
            summary_model="probe-model",
            summary_api_key="probe-key",
        ),
        actor_id="admin",
    )
    integrations = OptionalIntegrations(
        Settings(model_mode="remote"),
        config_store=store,
        client_factory=lambda **kwargs: httpx.Client(
            transport=httpx.MockTransport(handler), **kwargs
        ),
    )
    result = integrations.test_summary()
    assert result.ok is False
    assert "连接失败" in result.detail
    assert "503" in result.detail
    assert result.attempts == 2
    assert len(requests) == 2


def test_planner_connection_probe_uses_selected_protocol() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/responses"):
            return httpx.Response(200, json={"output_text": "OK"})
        if request.url.path.endswith("/messages"):
            return httpx.Response(
                200,
                json={"content": [{"type": "text", "text": "OK"}]},
            )
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "OK"}}]},
        )

    settings = Settings(model_mode="remote")
    for protocol, base_url in (
        ("openai_responses", "https://planner.local/v1"),
        ("openai_chat_completions", "https://planner.local/v1"),
        ("anthropic_messages", "https://planner.local/v1"),
    ):
        store = _store()
        store.update(
            IntegrationUpdate(
                planner_protocol=protocol,
                planner_base_url=base_url,
                planner_model="planner-probe-model",
                planner_api_key="planner-probe-key",
            ),
            actor_id="admin",
        )
        integrations = OptionalIntegrations(
            settings,
            config_store=store,
            client_factory=lambda **kwargs: httpx.Client(
                transport=httpx.MockTransport(handler),
                **kwargs,
            ),
        )
        result = integrations.test_planner()
        assert result.ok is True, result.detail
        assert result.detail == "连接成功，模型 planner-probe-model 已返回响应"
        assert result.attempts == 1

    assert len(requests) == 3
    assert requests[0].url.path.endswith("/responses")
    assert requests[1].url.path.endswith("/chat/completions")
    assert requests[2].url.path.endswith("/messages")
    assert requests[2].headers["x-api-key"] == "planner-probe-key"


def test_planner_secret_is_encrypted_and_not_returned_publicly() -> None:
    store = _store()
    updated = store.update(
        IntegrationUpdate(
            planner_protocol="anthropic_messages",
            planner_base_url="https://planner.local/anthropic",
            planner_model="planner-model",
            planner_api_key="planner-secret-value-123456",
        ),
        actor_id="admin-1",
    )

    assert updated.planner_api_key_configured is True
    assert updated.planner_api_key_hint == "已配置"
    assert not hasattr(updated, "planner_api_key")
    assert store.secrets()["planner_api_key"] == "planner-secret-value-123456"
    assert "planner-secret-value-123456" not in json.dumps(store.raw())


def test_planner_connection_probe_reuses_configured_summary_credentials() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "OK"}}]},
        )

    store = _store()
    store.update(
        IntegrationUpdate(
            summary_protocol="openai_chat_completions",
            summary_base_url="https://summary.local/v1",
            summary_model="summary-model",
            summary_api_key="summary-key",
        ),
        actor_id="admin",
    )
    integrations = OptionalIntegrations(
        Settings(model_mode="remote"),
        config_store=store,
        client_factory=lambda **kwargs: httpx.Client(
            transport=httpx.MockTransport(handler),
            **kwargs,
        ),
    )

    result = integrations.test_planner()

    assert result.ok is True, result.detail
    assert result.detail.startswith("规划模型复用总结 API：")
    assert "summary-model" in result.detail


def test_external_http_clients_ignore_process_proxy_by_default() -> None:
    captured: list[dict[str, object]] = []

    def client_factory(**kwargs: object) -> httpx.Client:
        captured.append(kwargs)
        return httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json={"choices": [{"message": {"content": "OK"}}]},
                )
            ),
            **kwargs,
        )

    store = _store()
    store.update(
        IntegrationUpdate(
            summary_enabled=True,
            summary_protocol="openai_chat_completions",
            summary_base_url="https://summary.local/v1",
            summary_model="probe-model",
            summary_api_key="probe-key",
        ),
        actor_id="admin",
    )
    result = OptionalIntegrations(
        Settings(model_mode="remote"),
        config_store=store,
        client_factory=client_factory,
    ).test_summary()

    assert result.ok is True, result.detail
    assert captured[0]["trust_env"] is False
    assert "proxy" not in captured[0]


def test_search_connection_probe_stops_after_first_available_provider() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "api.search.brave.com":
            return httpx.Response(200, json={"web": {"results": []}})
        if request.url.host == "api.tavily.com":
            return httpx.Response(
                200,
                json={"results": [{"title": "Guideline", "url": "https://example.test/g", "content": "evidence"}]},
            )
        return httpx.Response(
            503,
            json={"error": "unavailable"},
        )

    store = _store()
    store.update(
        IntegrationUpdate(
            web_search_enabled=True,
            web_search_max_results=5,
            search_provider_order=["brave", "tavily"],
            brave_search_api_key="brave-key",
            tavily_api_key="tavily-key",
        ),
        actor_id="admin",
    )
    integrations = OptionalIntegrations(
        Settings(model_mode="remote"),
        config_store=store,
        client_factory=lambda **kwargs: httpx.Client(
            transport=httpx.MockTransport(handler), **kwargs
        ),
    )
    result = integrations.test_search()
    assert result.ok is True, result.detail
    assert result.provider == "tavily"
    assert result.attempts == 2
    assert len(requests) == 2


def test_search_provider_adapters() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host == "search.local":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {"title": "SearXNG", "url": "https://source.test/s", "content": "s"}
                    ]
                },
            )
        if host == "www.googleapis.com":
            assert request.url.params["cx"] == "engine-id"
            return httpx.Response(
                200,
                json={
                    "items": [
                        {"title": "Google", "link": "https://source.test/g", "snippet": "g"}
                    ]
                },
            )
        if host == "api.bing.microsoft.com":
            return httpx.Response(
                200,
                json={
                    "webPages": {
                        "value": [
                            {"name": "Bing", "url": "https://source.test/b", "snippet": "b"}
                        ]
                    }
                },
            )
        if host == "api.exa.ai":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "title": "Exa",
                            "url": "https://source.test/e",
                            "text": "e",
                            "score": 0.8,
                        }
                    ]
                },
            )
        if host == "api.perplexity.ai":
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "p"}}],
                    "citations": ["https://source.test/p"],
                },
            )
        return httpx.Response(404)

    store = _store()
    store.update(
        IntegrationUpdate(
            web_search_enabled=True,
            web_search_max_results=5,
            search_provider_order=[
                "google_cse",
                "bing",
                "exa",
                "perplexity",
                "searxng",
            ],
            google_cse_api_key="google-key",
            google_cse_id="engine-id",
            bing_search_api_key="bing-key",
            exa_api_key="exa-key",
            perplexity_api_key="perplexity-key",
            searxng_base_url="https://search.local",
        ),
        actor_id="admin",
    )
    integrations = OptionalIntegrations(
        Settings(model_mode="remote"),
        config_store=store,
        client_factory=lambda **kwargs: httpx.Client(
            transport=httpx.MockTransport(handler), **kwargs
        ),
    )
    for provider in (
        "google_cse",
        "bing",
        "exa",
        "perplexity",
        "searxng",
    ):
        results = integrations._run_search_provider(provider, "uveitis")
        assert results and results[0].provider == provider


def test_domestic_search_provider_adapters() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer domestic-key"
        body = json.loads(request.content)
        host = request.url.host
        if host == "api.bochaai.com":
            assert request.url.path == "/v1/web-search"
            assert body["query"] == "uveitis"
            assert body["summary"] is True
            return httpx.Response(
                200,
                json={
                    "data": {
                        "webPages": {
                            "value": [
                                {
                                    "name": "Bocha",
                                    "url": "https://source.test/bocha",
                                    "summary": "b",
                                }
                            ]
                        }
                    }
                },
            )
        if host == "open.bigmodel.cn":
            assert request.url.path == "/api/paas/v4/web_search"
            assert body["search_engine"] == "search_std"
            return httpx.Response(
                200,
                json={
                    "search_result": [
                        {
                            "title": "Zhipu",
                            "link": "https://source.test/zhipu",
                            "content": "z",
                        }
                    ]
                },
            )
        if host == "qianfan.baidubce.com":
            assert request.url.path == "/v2/ai_search"
            assert body["messages"][0]["content"] == "uveitis"
            return httpx.Response(
                200,
                json={
                    "references": [
                        {
                            "title": "Qianfan",
                            "url": "https://source.test/qianfan",
                            "content": "q",
                        }
                    ]
                },
            )
        return httpx.Response(404)

    store = _store()
    store.update(
        IntegrationUpdate(
            web_search_enabled=True,
            search_provider_order=["bocha", "zhipu", "baidu_qianfan"],
            bocha_api_key="domestic-key",
            zhipu_search_api_key="domestic-key",
            baidu_qianfan_api_key="domestic-key",
        ),
        actor_id="admin",
    )
    assert "domestic-key" not in json.dumps(store.raw())
    integrations = OptionalIntegrations(
        Settings(model_mode="remote"),
        config_store=store,
        client_factory=lambda **kwargs: httpx.Client(
            transport=httpx.MockTransport(handler), **kwargs
        ),
    )
    for provider in ("bocha", "zhipu", "baidu_qianfan"):
        results = integrations._run_search_provider(provider, "uveitis")
        assert results and results[0].provider == provider
        assert results[0].url.startswith("https://source.test/")


def test_config_update_encrypts_secret_and_checks_revision() -> None:
    store = _store()
    updated = store.update(
        IntegrationUpdate(summary_api_key="secret-value-123456"),
        actor_id="admin-1",
    )
    assert updated.summary_api_key_configured is True
    assert not hasattr(updated, "summary_api_key")
    assert updated.revision == 1
    assert store.secrets()["summary_api_key"] == "secret-value-123456"
    assert "secret-value-123456" not in json.dumps(store.raw())

    with pytest.raises(ValueError, match="刷新后重试"):
        store.update(
            IntegrationUpdate(
                summary_model="next-model",
                expected_revision=0,
            ),
            actor_id="admin-2",
        )

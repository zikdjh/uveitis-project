from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

import httpx

from app.core.config import Settings
from app.schemas.case import CaseRead, Evidence, WebEvidence
from app.schemas.integrations import IntegrationConfigRead
from app.core.external_boundary import (
    BOUNDARY_ALLOW_CASE_DATA,
    BOUNDARY_SERVICE,
    assert_external_text,
    external_request_guard,
    prepare_external_payload,
)
from app.services.integration_settings import integration_defaults


IntegrationStatus = Literal["completed", "skipped", "failed"]


@dataclass
class IntegrationResult:
    status: IntegrationStatus
    detail: str
    data: dict[str, Any] = field(default_factory=dict)
    latency_ms: int = 0


@dataclass
class IntegrationTestOutcome:
    ok: bool
    detail: str
    latency_ms: int = 0
    provider: str | None = None
    attempts: int = 0


def _json_object(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else None
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        payload = json.loads(text[start : end + 1])
        return payload if isinstance(payload, dict) else None
    except json.JSONDecodeError:
        return None


def _summary_from_unparsed_json(text: str) -> str:
    """Recover the summary string when a model response is truncated JSON."""

    match = re.search(r'"summary"\s*:\s*"((?:\\.|[^"\\])*)"', text)
    if match is None:
        return text.strip()
    try:
        return str(json.loads(f'"{match.group(1)}"')).strip()
    except json.JSONDecodeError:
        return match.group(1).strip()


def _confidence(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, number))


def _score(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, number))


def _normalize_findings(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    findings: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            findings.append({"label": item.strip(), "confidence": 0.0})
        elif isinstance(item, dict):
            label = str(
                item.get("label")
                or item.get("finding")
                or item.get("name")
                or ""
            ).strip()
            if not label:
                continue
            findings.append(
                {
                    "label": label,
                    "location": str(item.get("location") or "").strip(),
                    "confidence": _confidence(item.get("confidence")),
                }
            )
    return findings


def _normalize_recommendations(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = str(item).strip()
        if text and text not in result:
            result.append(text)
    return result


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _safe_judgment(value: dict[str, Any]) -> dict[str, Any]:
    """Project a model judgment onto the fields allowed to leave the app."""

    return {
        "label": _safe_text(value.get("label")),
        "confidence": _confidence(value.get("confidence")),
        "findings": [
            {
                "label": item["label"],
                "location": item.get("location", ""),
                "confidence": item["confidence"],
            }
            for item in _normalize_findings(value.get("findings"))
        ],
    }


def _safe_decision(value: dict[str, Any]) -> dict[str, Any]:
    """Project a decision result onto the fields allowed to leave the app."""

    differential: list[dict[str, Any]] = []
    for item in value.get("differential") or value.get("differentials") or []:
        if isinstance(item, dict):
            label = _safe_text(item.get("label") or item.get("class"))
            if label:
                differential.append(
                    {
                        "label": label,
                        "confidence": _confidence(item.get("confidence")),
                    }
                )
    urgency = _safe_text(value.get("urgency") or "unknown").lower()
    if urgency not in {"low", "medium", "high", "unknown"}:
        urgency = "unknown"
    return {
        "primary_class": _safe_text(
            value.get("primary_class")
            or value.get("label")
        ),
        "confidence": _confidence(value.get("confidence")),
        "differential": differential,
        "urgency": urgency,
    }


class OptionalIntegrations:
    """HTTP adapters for optional model, search and summarization services."""

    def __init__(
        self,
        settings: Settings,
        client_factory: Callable[..., httpx.Client] = httpx.Client,
        config_store: Any | None = None,
    ) -> None:
        self.settings = settings
        self.client_factory = client_factory
        self.config_store = config_store

    def _config(self) -> dict[str, Any]:
        if self.config_store is None:
            defaults = integration_defaults()
            defaults.update(
                {
                    "summary_enabled": self.settings.external_summary_enabled,
                    "summary_base_url": self.settings.external_summary_base_url,
                    "summary_model": self.settings.external_summary_model,
                    "summary_api_key": self.settings.external_summary_api_key,
                    "planner_protocol": self.settings.agent_planner_protocol,
                    "planner_base_url": self.settings.agent_planner_base_url,
                    "planner_model": self.settings.agent_planner_model,
                    "planner_api_key": self.settings.agent_planner_api_key,
                    "web_search_enabled": self.settings.web_search_enabled,
                    "web_search_max_results": self.settings.web_search_max_results,
                    "search_provider_order": [
                        item.strip()
                        for item in self.settings.web_search_providers.split(",")
                        if item.strip()
                    ],
                    "tavily_api_key": self.settings.tavily_api_key,
                    "brave_search_api_key": self.settings.brave_search_api_key,
                    "serper_api_key": self.settings.serper_api_key,
                    "google_cse_api_key": self.settings.google_cse_api_key,
                    "google_cse_id": self.settings.google_cse_id,
                    "bing_search_api_key": self.settings.bing_search_api_key,
                    "exa_api_key": self.settings.exa_api_key,
                    "perplexity_api_key": self.settings.perplexity_api_key,
                    "searxng_base_url": self.settings.searxng_base_url,
                    "summary_protocol": self.settings.external_summary_protocol,
                }
            )
            return defaults
        raw = self.config_store.raw()
        secrets = self.config_store.secrets()
        return {**raw, **secrets}

    def public_config(self) -> IntegrationConfigRead:
        if self.config_store is None:
            return IntegrationConfigRead()
        return self.config_store.public()

    def external_summary_credentials(self) -> dict[str, Any]:
        """Return the external summary endpoint configuration in clear text.

        Used by the tool-chain planner so that a deployment which already
        configured an external summary model does not need a second set of
        credentials. The returned key stays server-side.
        """

        config = self._config()
        return {
            "protocol": str(
                config.get("summary_protocol") or "openai_chat_completions"
            ),
            "base_url": str(config.get("summary_base_url") or ""),
            "model": str(config.get("summary_model") or ""),
            "api_key": str(config.get("summary_api_key") or ""),
        }

    def external_planner_credentials(self) -> dict[str, Any]:
        """Return administrator-managed AgentScope planner credentials."""

        config = self._config()
        return {
            "protocol": str(
                config.get("planner_protocol") or "openai_chat_completions"
            ),
            "base_url": str(config.get("planner_base_url") or ""),
            "model": str(config.get("planner_model") or ""),
            "api_key": str(config.get("planner_api_key") or ""),
        }

    def test_summary(self) -> IntegrationTestOutcome:
        return self._test_model_endpoint("summary")

    def test_planner(self) -> IntegrationTestOutcome:
        config = self._config()
        planner_fields = (
            "planner_base_url",
            "planner_model",
            "planner_api_key",
        )
        planner_partially_configured = any(
            str(config.get(key) or "").strip() for key in planner_fields
        )
        summary_configured = all(
            str(config.get(key) or "").strip()
            for key in ("summary_base_url", "summary_model", "summary_api_key")
        )
        if not planner_partially_configured and summary_configured:
            outcome = self._test_model_endpoint("summary")
            prefix = "规划模型复用总结 API："
            outcome.detail = prefix + outcome.detail
            return outcome
        return self._test_model_endpoint("planner")

    def _post_with_retry(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        timeout: float,
        headers: dict[str, str],
        attempts_out: list[int] | None = None,
    ) -> tuple[dict[str, Any], int]:
        last_error: Exception | None = None
        for attempt in range(1, 3):
            try:
                response = self._post(
                    url,
                    payload,
                    timeout=timeout,
                    headers=headers,
                )
                return response, attempt
            except Exception as exc:
                last_error = exc
                if attempts_out is not None:
                    attempts_out[0] = attempt
                if attempt == 1:
                    time.sleep(0.2)
        assert last_error is not None
        raise last_error

    def _test_model_endpoint(self, prefix: str) -> IntegrationTestOutcome:
        started = time.perf_counter()
        attempts = 1
        attempt_state = [1]
        try:
            config = self._config()
            missing = [
                label
                for key, label in (
                    (f"{prefix}_base_url", "API 地址"),
                    (f"{prefix}_model", "模型名称"),
                    (f"{prefix}_api_key", "API Key"),
                )
                if not str(config.get(key) or "").strip()
            ]
            if missing:
                raise ValueError("尚未配置：" + "、".join(missing))
            protocol = str(
                config.get(f"{prefix}_protocol") or "openai_chat_completions"
            )
            model = str(config.get(f"{prefix}_model") or "")
            url = str(config.get(f"{prefix}_base_url") or "").rstrip("/")
            api_key = str(config.get(f"{prefix}_api_key") or "")
            probe = "Reply with OK. Do not add any other text."
            if protocol == "anthropic_messages":
                if not url.endswith("/messages"):
                    url += "/messages"
                response, attempts = self._post_with_retry(
                    url,
                    {
                        "model": model,
                        "max_tokens": 16,
                        "messages": [{"role": "user", "content": probe}],
                    },
                    timeout=self.settings.summary_timeout_seconds,
                    headers={
                        "Accept": "application/json",
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                    },
                    attempts_out=attempt_state,
                )
                content = "".join(
                    str(item.get("text") or "")
                    for item in response.get("content") or []
                    if isinstance(item, dict)
                )
            elif protocol == "openai_responses":
                if not url.endswith("/responses"):
                    url += "/responses"
                response, attempts = self._post_with_retry(
                    url,
                    {"model": model, "input": probe, "max_output_tokens": 16},
                    timeout=self.settings.summary_timeout_seconds,
                    headers=self._headers(api_key),
                    attempts_out=attempt_state,
                )
                content = str(response.get("output_text") or "")
                if not content:
                    content = "".join(
                        str(part.get("text") or "")
                        for item in response.get("output") or []
                        if isinstance(item, dict)
                        for part in item.get("content") or []
                        if isinstance(part, dict) and part.get("type") == "output_text"
                    )
            else:
                if not url.endswith("/chat/completions"):
                    url += "/chat/completions"
                response, attempts = self._post_with_retry(
                    url,
                    {
                        "model": model,
                        "messages": [{"role": "user", "content": probe}],
                        "max_tokens": 16,
                    },
                    timeout=self.settings.summary_timeout_seconds,
                    headers=self._headers(api_key),
                    attempts_out=attempt_state,
                )
                choices = response.get("choices") or []
                content = ""
                if choices and isinstance(choices[0], dict):
                    content = str(choices[0].get("message", {}).get("content") or "")
            if not content.strip():
                raise ValueError("外部模型返回空响应")
            return IntegrationTestOutcome(
                True,
                f"连接成功，模型 {model} 已返回响应",
                int((time.perf_counter() - started) * 1000),
                attempts=attempts,
            )
        except Exception as exc:
            attempts = attempt_state[0]
            return IntegrationTestOutcome(
                False,
                f"连接失败：{type(exc).__name__}: {exc}",
                int((time.perf_counter() - started) * 1000),
                attempts=attempts,
            )

    def test_search(
        self, provider: str | None = None, query: str = "uveitis clinical guideline"
    ) -> IntegrationTestOutcome:
        started = time.perf_counter()
        config = self._config()
        providers = (
            [provider]
            if provider
            else [str(item).strip().lower() for item in config.get("search_provider_order", []) if str(item).strip()]
        )
        failures: list[str] = []
        attempts = 0
        for candidate in providers:
            attempts += 1
            try:
                if not self._search_provider_configured(candidate):
                    raise ValueError("尚未配置连接凭据")
                results = self._run_search_provider(candidate, query)
                if not results:
                    raise ValueError("服务返回成功但无结果")
                detail = f"连接成功，{candidate} 返回 {len(results)} 条结果"
                if len(providers) > 1:
                    detail += f"（已尝试 {attempts} 家）"
                return IntegrationTestOutcome(
                    True,
                    detail,
                    int((time.perf_counter() - started) * 1000),
                    provider=candidate,
                    attempts=attempts,
                )
            except Exception as exc:
                failures.append(f"{candidate}: {type(exc).__name__}: {exc}")
        if not failures:
            return IntegrationTestOutcome(False, "没有已保存的搜索服务商", 0)
        return IntegrationTestOutcome(
            False,
            "没有可用服务商：" + "; ".join(failures[:3]),
            int((time.perf_counter() - started) * 1000),
            attempts=attempts,
        )

    def _search_provider_configured(self, provider: str) -> bool:
        config = self._config()
        if provider == "searxng":
            return bool(str(config.get("searxng_base_url") or "").strip())
        if provider == "google_cse":
            return bool(
                str(config.get("google_cse_api_key") or "").strip()
                and str(config.get("google_cse_id") or "").strip()
            )
        key_by_provider = {
            "tavily": "tavily_api_key",
            "brave": "brave_search_api_key",
            "serper": "serper_api_key",
            "bing": "bing_search_api_key",
            "exa": "exa_api_key",
            "perplexity": "perplexity_api_key",
        }
        key = key_by_provider.get(provider)
        return bool(key and str(config.get(key) or "").strip())

    @property
    def qwen_available(self) -> bool:
        return bool(
            self.settings.model_mode == "remote"
            and self.settings.qwen_judgment_enabled
            and self.settings.perception_service_url.strip()
        )

    @property
    def decision_available(self) -> bool:
        return bool(
            self.settings.model_mode == "remote"
            and self.settings.decision_enabled
            and self.settings.decision_service_url.strip()
        )

    @property
    def summary_available(self) -> bool:
        config = self._config()
        return bool(
            self.settings.model_mode == "remote"
            and config.get("summary_enabled")
            and str(config.get("summary_base_url") or "").strip()
            and str(config.get("summary_model") or "").strip()
            and str(config.get("summary_api_key") or "").strip()
        )

    def _headers(self, api_key: str = "") -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        if self.settings.internal_service_token:
            headers["X-Internal-Service-Token"] = (
                self.settings.internal_service_token
            )
        return headers

    def _post(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        timeout: float,
        headers: dict[str, str] | None = None,
        service: str = "外部服务",
        allow_case_data: bool = False,
    ) -> dict[str, Any]:
        extensions = {
            BOUNDARY_ALLOW_CASE_DATA: allow_case_data,
            BOUNDARY_SERVICE: service,
        }
        with self.client_factory(**self._client_options(timeout)) as client:
            response = client.post(
                url,
                json=payload,
                headers=headers or self._headers(),
                extensions=extensions,
            )
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, dict):
            raise ValueError("服务响应不是 JSON 对象")
        return data

    def _get(
        self,
        url: str,
        *,
        timeout: float,
        params: dict[str, Any],
        headers: dict[str, str] | None = None,
        service: str = "外部服务",
        allow_case_data: bool = False,
    ) -> dict[str, Any]:
        extensions = {
            BOUNDARY_ALLOW_CASE_DATA: allow_case_data,
            BOUNDARY_SERVICE: service,
        }
        with self.client_factory(**self._client_options(timeout)) as client:
            response = client.get(
                url,
                params=params,
                headers=headers or self._headers(),
                extensions=extensions,
            )
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, dict):
            raise ValueError("服务响应不是 JSON 对象")
        return data

    def _client_options(self, timeout: float) -> dict[str, Any]:
        options: dict[str, Any] = {
            "timeout": timeout,
            "event_hooks": {"request": [external_request_guard]},
            "trust_env": self.settings.external_network_trust_env,
        }
        proxy = self.settings.external_network_proxy.strip()
        if proxy:
            options["proxy"] = proxy
        return options

    def qwen_judgment(self, case: CaseRead) -> IntegrationResult:
        if not self.qwen_available:
            return IntegrationResult("skipped", "Qwen 微调判断服务未配置")
        started = time.perf_counter()
        image_payloads: list[dict[str, Any]] = []
        case_dir = Path(self.settings.upload_dir) / case.id
        for image in case.images:
            image_payload = image.model_dump(mode="json")
            matches = list(case_dir.glob(f"{image.id}.*"))
            if matches:
                image_payload["local_path"] = str(matches[0].resolve())
            image_payloads.append(image_payload)
        payload = {
            "task": "oct_aux_4class",
            "case": {
                "case_id": case.id,
                "owner_id": case.owner_id,
                "patient_age": case.patient_age,
                "patient_sex": case.patient_sex,
                "complaint": case.complaint,
                "medical_history": case.medical_history,
                "affected_eye": case.affected_eye,
                "images": image_payloads,
            },
            "output_schema": {
                "label": "string",
                "confidence": "number between 0 and 1",
                "impression": "short string",
                "findings": [
                    {
                        "label": "string",
                        "location": "string",
                        "confidence": "number between 0 and 1",
                    }
                ],
                "requires_human_review": True,
            },
            "constraints": [
                "Only classify or describe visible evidence.",
                "Do not provide a definitive diagnosis.",
                "Return compact JSON only.",
            ],
        }
        try:
            url = self.settings.perception_service_url.rstrip("/") + "/v1/judge"
            response = self._post(
                url,
                payload,
                timeout=self.settings.perception_timeout_seconds,
                service="Qwen 模型服务",
                allow_case_data=True,
            )
            data = response.get("result") if isinstance(response.get("result"), dict) else response
            findings = _normalize_findings(data.get("findings"))
            label = str(
                data.get("label")
                or data.get("primary_class")
                or data.get("classification")
                or ""
            ).strip()
            impression = str(data.get("impression") or "").strip()
            if not findings and label:
                findings = [
                    {
                        "label": label,
                        "location": "",
                        "confidence": _confidence(data.get("confidence")),
                    }
                ]
            if not findings and not impression:
                raise ValueError("Qwen 判断响应为空")
            return IntegrationResult(
                "completed",
                "Qwen 微调判断已完成",
                {
                    "label": label,
                    "confidence": _confidence(data.get("confidence")),
                    "impression": impression,
                    "findings": findings,
                    "recommendations": _normalize_recommendations(
                        data.get("recommendations")
                    ),
                    "requires_human_review": bool(
                        data.get("requires_human_review", True)
                    ),
                    "runtime": {
                        "model": _safe_text(response.get("model")),
                        "adapter_sha256": _safe_text(
                            response.get("adapter_sha256")
                        ),
                        "latency_ms": response.get("latency_ms"),
                        "generated_at": _safe_text(
                            response.get("generated_at")
                        ),
                        "truncated": bool(response.get("truncated", False)),
                        "peak_allocated_gib": response.get(
                            "peak_allocated_gib"
                        ),
                        "peak_reserved_gib": response.get(
                            "peak_reserved_gib"
                        ),
                        "research_use_only": bool(
                            response.get("research_use_only", True)
                        ),
                    },
                },
                int((time.perf_counter() - started) * 1000),
            )
        except Exception as exc:
            return IntegrationResult(
                "failed",
                f"Qwen 微调判断不可用: {type(exc).__name__}: {exc}",
                latency_ms=int((time.perf_counter() - started) * 1000),
            )

    def decision(
        self,
        case: CaseRead,
        judgment: dict[str, Any],
        evidence: list[Evidence],
    ) -> IntegrationResult:
        if not self.decision_available:
            return IntegrationResult("skipped", "补充决策模型未启用")
        started = time.perf_counter()
        payload = {
            "case": {
                "case_id": case.id,
                "patient_age": case.patient_age,
                "patient_sex": case.patient_sex,
                "complaint": case.complaint,
                "medical_history": case.medical_history,
                "affected_eye": case.affected_eye,
            },
            "qwen_judgment": judgment,
            "rag_evidence": [item.model_dump(mode="json") for item in evidence],
            "constraints": [
                "This is an optional second opinion, not a definitive diagnosis.",
                "Return compact JSON only.",
            ],
        }
        try:
            url = self.settings.decision_service_url.rstrip("/") + "/v1/decide"
            response = self._post(
                url,
                payload,
                timeout=self.settings.integration_timeout_seconds,
                service="决策模型服务",
                allow_case_data=True,
            )
            data = response.get("result") if isinstance(response.get("result"), dict) else response
            primary = str(
                data.get("primary_class")
                or data.get("label")
                or data.get("impression")
                or ""
            ).strip()
            differential = data.get("differential") or data.get("differentials") or []
            normalized: list[dict[str, Any]] = []
            if isinstance(differential, list):
                for item in differential:
                    if isinstance(item, str):
                        normalized.append({"label": item, "confidence": 0.0})
                    elif isinstance(item, dict):
                        label = str(
                            item.get("label")
                            or item.get("class")
                            or item.get("name")
                            or ""
                        ).strip()
                        if label:
                            normalized.append(
                                {
                                    "label": label,
                                    "confidence": _confidence(item.get("confidence")),
                                }
                            )
            if not primary and not normalized:
                raise ValueError("决策模型响应为空")
            urgency = str(data.get("urgency") or "unknown").lower()
            if urgency not in {"low", "medium", "high", "unknown"}:
                urgency = "unknown"
            return IntegrationResult(
                "completed",
                "补充决策模型已完成",
                {
                    "primary_class": primary,
                    "confidence": _confidence(data.get("confidence")),
                    "differential": normalized,
                    "urgency": urgency,
                    "recommendations": _normalize_recommendations(
                        data.get("recommended_action") or data.get("recommendations")
                    ),
                },
                int((time.perf_counter() - started) * 1000),
            )
        except Exception as exc:
            return IntegrationResult(
                "failed",
                f"补充决策模型不可用: {type(exc).__name__}: {exc}",
                latency_ms=int((time.perf_counter() - started) * 1000),
            )

    def _search_query(
        self,
        case: CaseRead,
        judgment: dict[str, Any],
        decision: dict[str, Any],
    ) -> str:
        """Build a search query from model labels only.

        The case record is intentionally unused: complaints, history and
        other patient fields must never reach a third-party search API. The
        parameter is kept so the call site stays explicit.
        """

        del case
        terms: list[str] = []
        for item in judgment.get("findings", []):
            if isinstance(item, dict) and item.get("label"):
                terms.append(str(item["label"]))
        if judgment.get("label"):
            terms.append(str(judgment["label"]))
        if decision.get("primary_class"):
            terms.append(str(decision["primary_class"]))
        for item in decision.get("differential", []):
            if isinstance(item, dict) and item.get("label"):
                terms.append(str(item["label"]))
        unique = list(dict.fromkeys(term for term in terms if term.strip()))
        if not unique:
            return "uveitis differential diagnosis clinical guideline evidence"
        return " ".join(unique[:8]) + " uveitis clinical evidence"

    def web_search(
        self,
        case: CaseRead,
        judgment: dict[str, Any],
        decision: dict[str, Any],
    ) -> IntegrationResult:
        config = self._config()
        if self.settings.model_mode != "remote" or not config.get("web_search_enabled"):
            return IntegrationResult("skipped", "网络搜索 API 未启用")
        started = time.perf_counter()
        try:
            query = self._search_query(case, judgment, decision)
            query = assert_external_text(query, case, service="网络搜索")
        except Exception as exc:
            return IntegrationResult(
                "failed",
                f"网络搜索已阻止外发: {type(exc).__name__}: {exc}",
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        providers = [str(item).strip().lower() for item in config.get("search_provider_order", []) if str(item).strip()]
        results: list[WebEvidence] = []
        failures: list[str] = []
        used: list[str] = []
        for provider in providers:
            try:
                provider_results = self._run_search_provider(provider, query)
                used.append(provider)
                for item in provider_results:
                    if all(existing.url != item.url for existing in results):
                        results.append(item)
                    if len(results) >= int(config.get("web_search_max_results", 5)):
                        break
            except Exception as exc:
                failures.append(f"{provider}: {type(exc).__name__}: {exc}")
            if len(results) >= int(config.get("web_search_max_results", 5)):
                break
        if not results and failures:
            return IntegrationResult(
                "failed",
                "网络搜索失败: " + "; ".join(failures[:3]),
                {"query": query},
                int((time.perf_counter() - started) * 1000),
            )
        if not results:
            return IntegrationResult("skipped", "网络搜索未返回结果", {"query": query})
        return IntegrationResult(
            "completed",
            f"网络搜索已完成: {', '.join(used)}",
            {"query": query, "results": results},
            int((time.perf_counter() - started) * 1000),
        )

    def _run_search_provider(
        self, provider: str, query: str
    ) -> list[WebEvidence]:
        config = self._config()
        limit = max(1, min(10, int(config.get("web_search_max_results", 5))))
        if provider == "tavily":
            api_key = str(config.get("tavily_api_key") or "")
            if not api_key:
                raise ValueError("TAVILY_API_KEY 未配置")
            data = self._post(
                "https://api.tavily.com/search",
                {
                    "api_key": api_key,
                    "query": query,
                    "max_results": limit,
                    "search_depth": "basic",
                    "include_answer": False,
                },
                timeout=self.settings.integration_timeout_seconds,
                headers={"Accept": "application/json"},
            )
            return [
                WebEvidence(
                    title=str(item.get("title") or item.get("url") or "检索结果"),
                    url=str(item.get("url") or ""),
                    snippet=str(item.get("content") or item.get("raw_content") or ""),
                    provider=provider,
                    score=_score(item.get("score")),
                )
                for item in data.get("results", [])
                if isinstance(item, dict) and item.get("url")
            ]
        if provider == "brave":
            api_key = str(config.get("brave_search_api_key") or "")
            if not api_key:
                raise ValueError("BRAVE_SEARCH_API_KEY 未配置")
            data = self._get(
                "https://api.search.brave.com/res/v1/web/search",
                timeout=self.settings.integration_timeout_seconds,
                params={"q": query, "count": limit},
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": api_key,
                },
            )
            items = data.get("web", {}).get("results", [])
            return [
                WebEvidence(
                    title=str(item.get("title") or item.get("url") or "检索结果"),
                    url=str(item.get("url") or ""),
                    snippet=str(item.get("description") or ""),
                    provider=provider,
                )
                for item in items
                if isinstance(item, dict) and item.get("url")
            ]
        if provider == "serper":
            api_key = str(config.get("serper_api_key") or "")
            if not api_key:
                raise ValueError("SERPER_API_KEY 未配置")
            data = self._post(
                "https://google.serper.dev/search",
                {"q": query, "num": limit},
                timeout=self.settings.integration_timeout_seconds,
                headers={
                    "Accept": "application/json",
                    "X-API-KEY": api_key,
                },
            )
            return [
                WebEvidence(
                    title=str(item.get("title") or item.get("link") or "检索结果"),
                    url=str(item.get("link") or ""),
                    snippet=str(item.get("snippet") or ""),
                    provider=provider,
                )
                for item in data.get("organic", [])
                if isinstance(item, dict) and item.get("link")
            ]
        if provider == "searxng":
            base_url = str(config.get("searxng_base_url") or "")
            if not base_url:
                raise ValueError("SEARXNG_BASE_URL 未配置")
            data = self._get(
                base_url.rstrip("/") + "/search",
                timeout=self.settings.integration_timeout_seconds,
                params={"q": query, "format": "json"},
                headers={"Accept": "application/json"},
            )
            return [
                WebEvidence(
                    title=str(item.get("title") or item.get("url") or "检索结果"),
                    url=str(item.get("url") or ""),
                    snippet=str(item.get("content") or ""),
                    provider=provider,
                    score=_score(item.get("score")),
                )
                for item in data.get("results", [])
                if isinstance(item, dict) and item.get("url")
            ]
        if provider == "google_cse":
            api_key = str(config.get("google_cse_api_key") or "")
            engine_id = str(config.get("google_cse_id") or "")
            if not api_key or not engine_id:
                raise ValueError("Google CSE API Key 或搜索引擎 ID 未配置")
            data = self._get(
                "https://www.googleapis.com/customsearch/v1",
                timeout=self.settings.integration_timeout_seconds,
                params={"key": api_key, "cx": engine_id, "q": query, "num": limit},
                headers={"Accept": "application/json"},
            )
            return [
                WebEvidence(
                    title=str(item.get("title") or item.get("link") or "检索结果"),
                    url=str(item.get("link") or ""),
                    snippet=str(item.get("snippet") or ""),
                    provider=provider,
                )
                for item in data.get("items", [])
                if isinstance(item, dict) and item.get("link")
            ]
        if provider == "bing":
            api_key = str(config.get("bing_search_api_key") or "")
            if not api_key:
                raise ValueError("Bing Search API Key 未配置")
            data = self._get(
                "https://api.bing.microsoft.com/v7.0/search",
                timeout=self.settings.integration_timeout_seconds,
                params={"q": query, "count": limit},
                headers={"Accept": "application/json", "Ocp-Apim-Subscription-Key": api_key},
            )
            items = data.get("webPages", {}).get("value", [])
            return [
                WebEvidence(
                    title=str(item.get("name") or item.get("url") or "检索结果"),
                    url=str(item.get("url") or ""),
                    snippet=str(item.get("snippet") or ""),
                    provider=provider,
                )
                for item in items
                if isinstance(item, dict) and item.get("url")
            ]
        if provider == "exa":
            api_key = str(config.get("exa_api_key") or "")
            if not api_key:
                raise ValueError("Exa API Key 未配置")
            data = self._post(
                "https://api.exa.ai/search",
                {"query": query, "numResults": limit, "contents": {"text": {"maxCharacters": 1200}}},
                timeout=self.settings.integration_timeout_seconds,
                headers={"Accept": "application/json", "x-api-key": api_key},
            )
            return [
                WebEvidence(
                    title=str(item.get("title") or item.get("url") or "检索结果"),
                    url=str(item.get("url") or ""),
                    snippet=str(item.get("text") or item.get("summary") or ""),
                    provider=provider,
                    score=_score(item.get("score")),
                )
                for item in data.get("results", [])
                if isinstance(item, dict) and item.get("url")
            ]
        if provider == "perplexity":
            api_key = str(config.get("perplexity_api_key") or "")
            if not api_key:
                raise ValueError("Perplexity API Key 未配置")
            data = self._post(
                "https://api.perplexity.ai/chat/completions",
                {
                    "model": "sonar",
                    "messages": [{"role": "user", "content": query}],
                    "max_tokens": 800,
                },
                timeout=self.settings.integration_timeout_seconds,
                headers=self._headers(api_key),
            )
            choices = data.get("choices") or []
            citations = data.get("citations") or []
            answer = ""
            if choices and isinstance(choices[0], dict):
                answer = str(choices[0].get("message", {}).get("content") or "")
            return [
                WebEvidence(
                    title=f"Perplexity 检索结果 {index + 1}",
                    url=str(url),
                    snippet=answer[:1200],
                    provider=provider,
                )
                for index, url in enumerate(citations[:limit])
                if str(url).startswith(("http://", "https://"))
            ]
        raise ValueError(f"不支持的网络搜索提供方: {provider}")

    def external_summary(
        self,
        case: CaseRead,
        judgment: dict[str, Any],
        decision: dict[str, Any],
        evidence: list[Evidence],
        web_evidence: list[WebEvidence],
    ) -> IntegrationResult:
        if not self.summary_available:
            return IntegrationResult("skipped", "外部总结 API 未启用")
        started = time.perf_counter()
        config = self._config()
        # Images and the case record never leave the deployment: the payload
        # carries an explicit allowlist of model output and retrieved evidence
        # only; upstream dictionaries are never forwarded verbatim.
        try:
            payload: dict[str, Any] = {
                "judgment": _safe_judgment(judgment),
                "decision": _safe_decision(decision),
                "rag_evidence": [
                    item.model_dump(mode="json") for item in evidence[:8]
                ],
                "web_evidence": [
                    item.model_dump(mode="json") for item in web_evidence[:8]
                ],
            }
            payload = prepare_external_payload(payload, service="外部总结")
            assert_external_text(
                json.dumps(payload, ensure_ascii=False),
                case,
                service="外部总结",
            )
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You summarize structured ophthalmology research signals. "
                        "You are not the diagnostician. Do not invent facts, do not "
                        "make a definitive diagnosis, and do not add patient data. "
                        "Return compact JSON with keys summary, recommendations, "
                        "uncertainties, and evidence_ids."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(payload, ensure_ascii=False),
                },
            ]
            protocol = str(config.get("summary_protocol") or "openai_chat_completions")
            url = str(config.get("summary_base_url") or "").rstrip("/")
            model = str(config.get("summary_model") or "")
            api_key = str(config.get("summary_api_key") or "")
            if protocol == "anthropic_messages":
                if not url.endswith("/messages"):
                    url += "/messages"
                response = self._post(
                    url,
                    {
                        "model": model,
                        "max_tokens": 2400,
                        "temperature": 0.1,
                        "system": messages[0]["content"],
                        "messages": [messages[1]],
                    },
                    timeout=self.settings.summary_timeout_seconds,
                    headers={
                        "Accept": "application/json",
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                    },
                )
                blocks = response.get("content") or []
                content = "".join(
                    str(item.get("text") or "")
                    for item in blocks
                    if isinstance(item, dict)
                )
            elif protocol == "openai_responses":
                if not url.endswith("/responses"):
                    url += "/responses"
                response = self._post(
                    url,
                    {
                        "model": model,
                        "instructions": messages[0]["content"],
                        "input": messages[1]["content"],
                        "max_output_tokens": 2400,
                    },
                    timeout=self.settings.summary_timeout_seconds,
                    headers=self._headers(api_key),
                )
                content = response.get("output_text")
                if not content:
                    chunks: list[str] = []
                    for item in response.get("output") or []:
                        if not isinstance(item, dict):
                            continue
                        for part in item.get("content") or []:
                            if isinstance(part, dict) and part.get("type") == "output_text":
                                chunks.append(str(part.get("text") or ""))
                    content = "".join(chunks)
            else:
                if not url.endswith("/chat/completions"):
                    url += "/chat/completions"
                response = self._post(
                    url,
                    {
                        "model": model,
                        "messages": messages,
                        "temperature": 0.1,
                        "max_tokens": 2400,
                    },
                    timeout=self.settings.summary_timeout_seconds,
                    headers=self._headers(api_key),
                )
                choices = response.get("choices") or []
                if not choices or not isinstance(choices[0], dict):
                    raise ValueError("外部总结响应缺少 choices")
                content = choices[0].get("message", {}).get("content", "")
            parsed = _json_object(str(content)) if content else None
            if parsed is None and content:
                parsed = {"summary": _summary_from_unparsed_json(str(content))}
            if not parsed or not str(parsed.get("summary") or "").strip():
                raise ValueError("外部总结响应为空")
            return IntegrationResult(
                "completed",
                f"外部总结已完成: {config.get('summary_model')}",
                {
                    "summary": str(parsed.get("summary") or "").strip(),
                    "recommendations": _normalize_recommendations(
                        parsed.get("recommendations")
                    ),
                    "uncertainties": _normalize_recommendations(
                        parsed.get("uncertainties")
                    ),
                    "evidence_ids": _normalize_recommendations(
                        parsed.get("evidence_ids")
                    ),
                },
                int((time.perf_counter() - started) * 1000),
            )
        except Exception as exc:
            return IntegrationResult(
                "failed",
                f"外部总结不可用: {type(exc).__name__}: {exc}",
                latency_ms=int((time.perf_counter() - started) * 1000),
            )

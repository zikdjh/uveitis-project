from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import inspect, text

from app.core.secret_box import SecretBox
from app.db.data_dictionary import (
    REVISION_KEY,
    UPDATED_AT_KEY,
    UPDATED_BY_KEY,
    DataDictionaryStore,
    DictionaryValue,
    MemoryDataDictionaryStore,
)
from app.db.naming import column_name, table_name
from app.schemas.integrations import (
    IntegrationConfigRead,
    IntegrationConfigUpdate,
    SECRET_KEYS,
)


INTEGRATION_NAMESPACE = "integration"

DEFAULT_PROVIDER_ORDER = [
    "bocha",
    "zhipu",
    "baidu_qianfan",
    "tavily",
    "brave",
    "serper",
    "google_cse",
    "bing",
    "exa",
    "perplexity",
    "searxng",
]

PUBLIC_DEFAULTS: dict[str, Any] = {
    "summary_enabled": False,
    "summary_protocol": "openai_chat_completions",
    "summary_base_url": "",
    "summary_model": "",
    "planner_protocol": "openai_chat_completions",
    "planner_base_url": "",
    "planner_model": "",
    "web_search_enabled": False,
    "web_search_max_results": 5,
    "search_provider_order": DEFAULT_PROVIDER_ORDER,
    "google_cse_id": "",
    "searxng_base_url": "",
}

SECRET_FIELD_BY_KEY = {
    "summary_api_key": "summary_api_key_configured",
    "planner_api_key": "planner_api_key_configured",
    "tavily_api_key": "tavily_api_key_configured",
    "brave_search_api_key": "brave_search_api_key_configured",
    "serper_api_key": "serper_api_key_configured",
    "google_cse_api_key": "google_cse_api_key_configured",
    "bing_search_api_key": "bing_search_api_key_configured",
    "exa_api_key": "exa_api_key_configured",
    "perplexity_api_key": "perplexity_api_key_configured",
    "bocha_api_key": "bocha_api_key_configured",
    "zhipu_search_api_key": "zhipu_search_api_key_configured",
    "baidu_qianfan_api_key": "baidu_qianfan_api_key_configured",
}

CLEAR_FIELD_BY_KEY = {
    key: f"clear_{key}" for key in SECRET_KEYS
}

FIELD_TO_DICTIONARY_KEY = {
    "summary_enabled": "summary.enabled",
    "summary_protocol": "summary.protocol",
    "summary_base_url": "summary.base_url",
    "summary_model": "summary.model",
    "summary_api_key": "summary.api_key",
    "planner_protocol": "planner.protocol",
    "planner_base_url": "planner.base_url",
    "planner_model": "planner.model",
    "planner_api_key": "planner.api_key",
    "web_search_enabled": "search.enabled",
    "web_search_max_results": "search.max_results",
    "search_provider_order": "search.provider_order",
    "google_cse_id": "search.google_cse.id",
    "searxng_base_url": "search.searxng.base_url",
    "tavily_api_key": "search.tavily.api_key",
    "brave_search_api_key": "search.brave.api_key",
    "serper_api_key": "search.serper.api_key",
    "google_cse_api_key": "search.google_cse.api_key",
    "bing_search_api_key": "search.bing.api_key",
    "exa_api_key": "search.exa.api_key",
    "perplexity_api_key": "search.perplexity.api_key",
    "bocha_api_key": "search.bocha.api_key",
    "zhipu_search_api_key": "search.zhipu.api_key",
    "baidu_qianfan_api_key": "search.baidu_qianfan.api_key",
}

FIELD_VALUE_TYPES = {
    **{
        key: "bool"
        for key in (
            "summary_enabled",
            "web_search_enabled",
        )
    },
    "web_search_max_results": "int",
    "search_provider_order": "json",
    **{key: "secret" for key in SECRET_KEYS},
}

FIELD_DESCRIPTIONS = {
    "summary_enabled": "外部总结模型总开关",
    "summary_protocol": "外部总结接口协议",
    "summary_base_url": "外部总结 API 请求根路径",
    "summary_model": "外部总结模型名称",
    "summary_api_key": "外部总结 API Key",
    "planner_protocol": "AgentScope 规划模型接口协议",
    "planner_base_url": "AgentScope 规划模型请求根路径",
    "planner_model": "AgentScope 规划模型名称",
    "planner_api_key": "AgentScope 规划模型 API Key",
    "web_search_enabled": "网络搜索总开关",
    "web_search_max_results": "单次搜索最大结果数",
    "search_provider_order": "搜索服务商尝试顺序",
    "google_cse_id": "Google CSE 搜索引擎 ID",
    "searxng_base_url": "SearXNG 服务地址",
    "tavily_api_key": "Tavily API Key",
    "brave_search_api_key": "Brave Search API Key",
    "serper_api_key": "Serper API Key",
    "google_cse_api_key": "Google CSE API Key",
    "bing_search_api_key": "Bing Search API Key",
    "exa_api_key": "Exa API Key",
    "perplexity_api_key": "Perplexity API Key",
    "bocha_api_key": "博查 Bocha API Key",
    "zhipu_search_api_key": "智谱网络搜索 API Key",
    "baidu_qianfan_api_key": "百度千帆 AI 搜索 API Key",
}


def integration_defaults() -> dict[str, Any]:
    return {
        **PUBLIC_DEFAULTS,
        "search_provider_order": list(DEFAULT_PROVIDER_ORDER),
        **{key: "" for key in SECRET_KEYS},
        "revision": 0,
        "updated_at": None,
        "updated_by": "",
    }


def _raw_from_values(values: dict[str, Any]) -> dict[str, Any]:
    raw = integration_defaults()
    for field, dictionary_key in FIELD_TO_DICTIONARY_KEY.items():
        if dictionary_key in values:
            raw[field] = values[dictionary_key]
    raw["revision"] = int(values.get(REVISION_KEY, 0) or 0)
    raw["updated_at"] = values.get(UPDATED_AT_KEY)
    raw["updated_by"] = str(values.get(UPDATED_BY_KEY, "") or "")
    return raw


def _mutations_from_payload(
    payload: IntegrationConfigUpdate,
) -> dict[str, DictionaryValue]:
    values = payload.model_dump(exclude_none=True, exclude_unset=True)
    values.pop("expected_revision", None)
    mutations: dict[str, DictionaryValue] = {}
    for secret_key in SECRET_KEYS:
        secret = values.pop(secret_key, None)
        should_clear = bool(values.pop(CLEAR_FIELD_BY_KEY[secret_key], False))
        dictionary_key = FIELD_TO_DICTIONARY_KEY[secret_key]
        if secret is not None and str(secret).strip():
            mutations[dictionary_key] = DictionaryValue(
                value=str(secret).strip(),
                value_type="secret",
                description=FIELD_DESCRIPTIONS[secret_key],
            )
        elif should_clear:
            mutations[dictionary_key] = DictionaryValue(delete=True)
    for field, value in values.items():
        dictionary_key = FIELD_TO_DICTIONARY_KEY.get(field)
        if dictionary_key is None:
            continue
        mutations[dictionary_key] = DictionaryValue(
            value=value,
            value_type=FIELD_VALUE_TYPES.get(field),  # type: ignore[arg-type]
            description=FIELD_DESCRIPTIONS.get(field, field),
        )
    return mutations


class _DictionaryIntegrationSettingsStore:
    dictionary_store: Any

    def raw(self) -> dict[str, Any]:
        return _raw_from_values(
            self.dictionary_store.get_namespace_values(
                INTEGRATION_NAMESPACE,
                reveal_secret=False,
            )
        )

    def public(self) -> IntegrationConfigRead:
        return _public_view(self.raw())

    def secrets(self) -> dict[str, str]:
        values = self.dictionary_store.get_namespace_values(
            INTEGRATION_NAMESPACE,
            reveal_secret=True,
        )
        return {
            key: str(values.get(FIELD_TO_DICTIONARY_KEY[key], "") or "")
            for key in SECRET_KEYS
        }

    def update(
        self,
        payload: IntegrationConfigUpdate,
        *,
        actor_id: str,
    ) -> IntegrationConfigRead:
        current_revision = int(
            self.dictionary_store.get_value(
                INTEGRATION_NAMESPACE,
                REVISION_KEY,
                default=0,
            )
            or 0
        )
        if (
            payload.expected_revision is not None
            and payload.expected_revision != current_revision
        ):
            raise ValueError("配置已被其他管理员更新，请刷新后重试")
        self.dictionary_store.update_namespace(
            INTEGRATION_NAMESPACE,
            _mutations_from_payload(payload),
            actor_id=actor_id,
            expected_revision=current_revision,
        )
        return self.public()


class MemoryIntegrationSettingsStore(_DictionaryIntegrationSettingsStore):
    """In-memory integration settings backed by a data dictionary."""

    def __init__(
        self,
        secret_box: SecretBox,
        *,
        dictionary_store=None,
    ) -> None:
        self.dictionary_store = (
            dictionary_store or MemoryDataDictionaryStore(secret_box)
        )


class PostgresIntegrationSettingsStore(_DictionaryIntegrationSettingsStore):
    def __init__(
        self,
        session_factory,
        secret_box: SecretBox,
        *,
        dictionary_store=None,
    ) -> None:
        self._session_factory = session_factory
        self.dictionary_store = (
            dictionary_store or DataDictionaryStore(session_factory, secret_box)
        )
        self._migrate_legacy_settings()

    def _migrate_legacy_settings(self) -> None:
        current_revision = self.dictionary_store.get_value(
            INTEGRATION_NAMESPACE,
            REVISION_KEY,
            default=None,
        )
        if current_revision is not None:
            return
        engine = self._session_factory.kw["bind"]
        legacy_table = table_name("integration_setting")
        if legacy_table not in inspect(engine).get_table_names():
            return
        payload_column = column_name("payload_json")
        id_column = column_name("id")
        with self._session_factory() as session:
            row = session.execute(
                text(
                    f'SELECT "{payload_column}" FROM "{legacy_table}" '
                    f'WHERE "{id_column}" = 1'
                )
            ).fetchone()
        if row is None:
            return
        raw_value = row[0]
        legacy = json.loads(
            raw_value if isinstance(raw_value, str) else str(raw_value)
        )
        values: dict[str, DictionaryValue] = {}
        for field, dictionary_key in FIELD_TO_DICTIONARY_KEY.items():
            value = legacy.get(field)
            if field in SECRET_KEYS:
                if str(value or "").strip():
                    values[dictionary_key] = DictionaryValue(
                        value="",
                        value_type="secret",
                        description=FIELD_DESCRIPTIONS[field],
                        stored_value=str(value),
                    )
                continue
            if value is None:
                continue
            values[dictionary_key] = DictionaryValue(
                value=value,
                value_type=FIELD_VALUE_TYPES.get(field),  # type: ignore[arg-type]
                description=FIELD_DESCRIPTIONS.get(field, field),
            )
        updated_at = None
        if legacy.get("updated_at"):
            try:
                updated_at = datetime.fromisoformat(str(legacy["updated_at"]))
            except ValueError:
                updated_at = None
        self.dictionary_store.update_namespace(
            INTEGRATION_NAMESPACE,
            values,
            actor_id=str(legacy.get("updated_by") or "legacy-migration"),
            revision=int(legacy.get("revision", 0) or 0),
            updated_at=updated_at or datetime.now(UTC),
            updated_by=str(legacy.get("updated_by") or "legacy-migration"),
        )


def _public_view(raw: dict[str, Any]) -> IntegrationConfigRead:
    payload = dict(PUBLIC_DEFAULTS)
    payload.update(
        {key: raw.get(key, value) for key, value in PUBLIC_DEFAULTS.items()}
    )
    for key, configured_key in SECRET_FIELD_BY_KEY.items():
        encrypted = str(raw.get(key) or "")
        payload[configured_key] = bool(encrypted)
        payload[key.replace("_api_key", "_api_key_hint")] = (
            "已配置" if encrypted else ""
        )
    payload.update(
        {
            "revision": int(raw.get("revision", 0)),
            "updated_at": raw.get("updated_at") or None,
            "updated_by": str(raw.get("updated_by") or ""),
        }
    )
    return IntegrationConfigRead.model_validate(payload)

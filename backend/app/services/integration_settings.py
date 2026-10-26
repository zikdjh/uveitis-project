from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import inspect, text

from app.schemas.integrations import IntegrationConfigRead, IntegrationConfigUpdate, SECRET_KEYS


DEFAULT_PROVIDER_ORDER = [
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
    "summary_include_clinical_text": False,
    "web_search_enabled": False,
    "web_search_include_complaint": False,
    "web_search_max_results": 5,
    "search_provider_order": DEFAULT_PROVIDER_ORDER,
    "google_cse_id": "",
    "searxng_base_url": "",
}

SECRET_FIELD_BY_KEY = {
    "summary_api_key": "summary_api_key_configured",
    "tavily_api_key": "tavily_api_key_configured",
    "brave_search_api_key": "brave_search_api_key_configured",
    "serper_api_key": "serper_api_key_configured",
    "google_cse_api_key": "google_cse_api_key_configured",
    "bing_search_api_key": "bing_search_api_key_configured",
    "exa_api_key": "exa_api_key_configured",
    "perplexity_api_key": "perplexity_api_key_configured",
}

CLEAR_FIELD_BY_KEY = {
    key: f"clear_{key}" for key in SECRET_KEYS
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


class SecretBox:
    """Authenticated AES-GCM encryption with a deployment-held master key."""

    def __init__(self, key_material: str) -> None:
        if len(key_material) < 32:
            raise ValueError("APP_INTEGRATION_SECRET_KEY 至少需要 32 个字符")
        self.key = hashlib.sha256(key_material.encode("utf-8")).digest()

    def encrypt(self, value: str) -> str:
        if not value:
            return ""
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        except ImportError as exc:
            raise RuntimeError("服务配置加密依赖 cryptography 未安装") from exc
        nonce = os.urandom(12)
        ciphertext = AESGCM(self.key).encrypt(nonce, value.encode("utf-8"), None)
        return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")

    def decrypt(self, value: str) -> str:
        if not value:
            return ""
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        except ImportError as exc:
            raise RuntimeError("服务配置加密依赖 cryptography 未安装") from exc
        try:
            packed = base64.urlsafe_b64decode(value.encode("ascii"))
            return AESGCM(self.key).decrypt(
                packed[:12], packed[12:], None
            ).decode("utf-8")
        except Exception as exc:
            raise ValueError("服务密钥解密失败，请检查 APP_INTEGRATION_SECRET_KEY") from exc


class MemoryIntegrationSettingsStore:
    """In-memory integration configuration used by isolated tests."""

    def __init__(self, secret_box: SecretBox) -> None:
        self.secret_box = secret_box
        self._payload = integration_defaults()

    def raw(self) -> dict[str, Any]:
        return dict(self._payload)

    def public(self) -> IntegrationConfigRead:
        return _public_view(self.raw())

    def secrets(self) -> dict[str, str]:
        return {
            key: self.secret_box.decrypt(str(self._payload.get(key) or ""))
            for key in SECRET_KEYS
        }

    def update(
        self,
        payload: IntegrationConfigUpdate,
        *,
        actor_id: str,
    ) -> IntegrationConfigRead:
        current = dict(self._payload)
        revision = int(current.get("revision", 0))
        if (
            payload.expected_revision is not None
            and payload.expected_revision != revision
        ):
            raise ValueError("配置已被其他管理员更新，请刷新后重试")
        values = payload.model_dump(exclude_none=True, exclude_unset=True)
        for key in SECRET_KEYS:
            value = values.pop(key, None)
            if value is not None and str(value).strip():
                current[key] = self.secret_box.encrypt(str(value).strip())
            if values.pop(CLEAR_FIELD_BY_KEY[key], False):
                current[key] = ""
        values.pop("expected_revision", None)
        current.update(values)
        current["revision"] = revision + 1
        current["updated_at"] = datetime.now(UTC).isoformat()
        current["updated_by"] = actor_id
        self._payload = current
        return _public_view(current)


class PostgresIntegrationSettingsStore:
    def __init__(self, session_factory, secret_box: SecretBox) -> None:
        self._session_factory = session_factory
        self.secret_box = secret_box
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        engine = self._session_factory.kw["bind"]
        inspector = inspect(engine)
        if "integration_settings" in inspector.get_table_names():
            return
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE integration_settings (
                        id INTEGER PRIMARY KEY,
                        revision INTEGER NOT NULL,
                        payload_json TEXT NOT NULL,
                        updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
                        updated_by VARCHAR(36) NOT NULL
                    )
                    """
                )
            )

    def _row(self) -> dict[str, Any] | None:
        with self._session_factory() as session:
            row = session.execute(
                text(
                    "SELECT payload_json FROM integration_settings WHERE id = 1"
                )
            ).fetchone()
        if row is None:
            return None
        value = row[0]
        return json.loads(value if isinstance(value, str) else str(value))

    def raw(self) -> dict[str, Any]:
        return self._row() or integration_defaults()

    def public(self) -> IntegrationConfigRead:
        return _public_view(self.raw())

    def secrets(self) -> dict[str, str]:
        raw = self.raw()
        return {
            key: self.secret_box.decrypt(str(raw.get(key) or ""))
            for key in SECRET_KEYS
        }

    def update(
        self,
        payload: IntegrationConfigUpdate,
        *,
        actor_id: str,
    ) -> IntegrationConfigRead:
        with self._session_factory.begin() as session:
            row = session.execute(
                text(
                    "SELECT payload_json FROM integration_settings "
                    "WHERE id = 1 FOR UPDATE"
                )
            ).fetchone()
            current = (
                json.loads(row[0]) if row else integration_defaults()
            )
            current_revision = int(current.get("revision", 0))
            if (
                payload.expected_revision is not None
                and payload.expected_revision != current_revision
            ):
                raise ValueError("配置已被其他管理员更新，请刷新后重试")
            values = payload.model_dump(exclude_none=True, exclude_unset=True)
            for key in SECRET_KEYS:
                value = values.pop(key, None)
                if value is not None and str(value).strip():
                    current[key] = self.secret_box.encrypt(str(value).strip())
                if values.pop(CLEAR_FIELD_BY_KEY[key], False):
                    current[key] = ""
            values.pop("expected_revision", None)
            current.update(values)
            current["revision"] = current_revision + 1
            current["updated_at"] = datetime.now(UTC).isoformat()
            current["updated_by"] = actor_id
            session.execute(
                text(
                    """
                    INSERT INTO integration_settings
                        (id, revision, payload_json, updated_at, updated_by)
                    VALUES (1, :revision, :payload, :updated_at, :updated_by)
                    ON CONFLICT (id) DO UPDATE SET
                        revision = EXCLUDED.revision,
                        payload_json = EXCLUDED.payload_json,
                        updated_at = EXCLUDED.updated_at,
                        updated_by = EXCLUDED.updated_by
                    """
                ),
                {
                    "revision": current["revision"],
                    "payload": json.dumps(current, ensure_ascii=False),
                    "updated_at": datetime.now(UTC),
                    "updated_by": actor_id,
                },
            )
        return _public_view(current)


def _public_view(raw: dict[str, Any]) -> IntegrationConfigRead:
    payload = dict(PUBLIC_DEFAULTS)
    payload.update({key: raw.get(key, value) for key, value in PUBLIC_DEFAULTS.items()})
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

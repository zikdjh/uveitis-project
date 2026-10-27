from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.core.secret_box import SecretBox
from app.db.data_dictionary import DataDictionaryStore
from app.db.postgres import PostgresCaseStore
from app.schemas.case import CaseRead


TEST_DATABASE_URL = os.getenv("APP_TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="设置 APP_TEST_DATABASE_URL 后运行 PostgreSQL 仓储契约测试",
)


def test_postgres_case_store_round_trip() -> None:
    store = PostgresCaseStore(TEST_DATABASE_URL, connect_timeout_seconds=3)
    now = datetime.now(UTC)
    case = CaseRead(
        id=str(uuid4()),
        patient_age=42,
        patient_sex="F",
        complaint="PostgreSQL 仓储契约测试",
        medical_history="无特殊",
        affected_eye="OS",
        consent_confirmed=True,
        status="created",
        created_at=now,
        updated_at=now,
    )

    store.save(case)
    loaded = store.get(case.id)

    assert loaded is not None
    assert loaded.id == case.id
    assert loaded.status == "created"
    assert store.ping() is True


def test_postgres_data_dictionary_encrypts_and_redacts_secrets() -> None:
    case_store = PostgresCaseStore(TEST_DATABASE_URL, connect_timeout_seconds=3)
    dictionary = DataDictionaryStore(
        case_store._session_factory,
        SecretBox("postgres-contract-integration-master-key-32chars"),
    )
    namespace = f"contract-{uuid4().hex}"
    entry = dictionary.set_value(
        namespace,
        "api.key",
        "contract-secret-value",
        value_type="secret",
        description="PostgreSQL 数据字典契约测试",
        actor_id="contract-test",
    )

    assert entry.is_secret is True
    assert entry.value is None
    assert dictionary.get_value(namespace, "api.key") == "contract-secret-value"
    stored = dictionary.get_namespace_values(namespace, reveal_secret=False)
    assert stored["api.key"] != "contract-secret-value"
    assert dictionary.delete_value(
        namespace,
        "api.key",
        actor_id="contract-test",
        expected_revision=entry.revision,
    )

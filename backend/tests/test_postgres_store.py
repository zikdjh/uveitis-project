from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest

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

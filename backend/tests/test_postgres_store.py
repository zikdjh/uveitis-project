from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.core.config import Settings
from app.core.secret_box import SecretBox
from app.db.models import AnalysisJobRow, CaseRow
from app.db.analysis_jobs import PostgresAnalysisJobStore
from app.db.data_dictionary import DataDictionaryStore
from app.db.postgres import PostgresCaseStore
from app.schemas.case import CaseRead
from app.services.analysis import AnalysisService
from app.services.analysis_jobs import AnalysisJobService


TEST_DATABASE_URL = os.getenv("APP_TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="设置 APP_TEST_DATABASE_URL 后运行 PostgreSQL 仓储契约测试",
)


@pytest.fixture(autouse=True)
def cleanup_contract_rows():
    yield
    if not TEST_DATABASE_URL:
        return
    store = PostgresCaseStore(TEST_DATABASE_URL, connect_timeout_seconds=3)
    case_keys = select(CaseRow.case_key).where(
        CaseRow.owner_id == "contract-doctor"
    )
    with store._session_factory.begin() as session:
        session.execute(
            delete(AnalysisJobRow).where(
                AnalysisJobRow.case_id.in_(case_keys)
            )
        )
        session.execute(
            delete(CaseRow).where(CaseRow.owner_id == "contract-doctor")
        )


def test_postgres_case_store_round_trip() -> None:
    store = PostgresCaseStore(TEST_DATABASE_URL, connect_timeout_seconds=3)
    now = datetime.now(UTC)
    case = CaseRead(
        id=str(uuid4()),
        owner_id="contract-doctor",
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


def test_postgres_analysis_job_lease_round_trip() -> None:
    case_store = PostgresCaseStore(TEST_DATABASE_URL, connect_timeout_seconds=3)
    now = datetime.now(UTC)
    case = CaseRead(
        id=str(uuid4()),
        owner_id="contract-doctor",
        patient_age=42,
        patient_sex="F",
        complaint="分析任务仓储契约测试",
        medical_history="",
        affected_eye="OS",
        consent_confirmed=True,
        status="analyzing",
        created_at=now,
        updated_at=now,
    )
    case_store.save(case)
    jobs = PostgresAnalysisJobStore(case_store._session_factory)
    job = jobs.enqueue(case.id, max_attempts=2)

    claimed = jobs.claim(
        "contract-worker",
        now=now,
        lease_seconds=30,
        job_key=job.job_key,
    )
    assert claimed is not None
    assert claimed.job_key == job.job_key
    assert claimed.attempt_count == 1
    jobs.complete(claimed.job_key)
    assert jobs.get(job.job_key).status == "completed"


def test_postgres_analysis_job_renews_only_current_owner() -> None:
    case_store = PostgresCaseStore(TEST_DATABASE_URL, connect_timeout_seconds=3)
    now = datetime.now(UTC)
    case = CaseRead(
        id=str(uuid4()),
        owner_id="contract-doctor",
        patient_age=42,
        patient_sex="F",
        complaint="分析任务续租契约测试",
        medical_history="",
        affected_eye="OS",
        consent_confirmed=True,
        status="analyzing",
        created_at=now,
        updated_at=now,
    )
    case_store.save(case)
    jobs = PostgresAnalysisJobStore(case_store._session_factory)
    job = jobs.enqueue(case.id, max_attempts=2)
    claimed = jobs.claim(
        "contract-worker",
        now=now,
        lease_seconds=30,
        job_key=job.job_key,
    )
    assert claimed is not None
    original_expiry = claimed.lease_expires_at

    renew_at = datetime.now(UTC)
    assert jobs.renew(
        job.job_key,
        "other-worker",
        now=renew_at,
        lease_seconds=30,
    ) is False
    assert jobs.renew(
        job.job_key,
        "contract-worker",
        now=renew_at,
        lease_seconds=30,
    ) is True
    renewed = jobs.get(job.job_key)
    assert renewed is not None
    assert renewed.lease_expires_at >= renew_at + timedelta(seconds=29)
    assert renewed.lease_expires_at > original_expiry
    finalizing = jobs.begin_finalize(
        job.job_key,
        "contract-worker",
        now=datetime.now(UTC),
    )
    assert finalizing is not None and finalizing.status == "finalizing"
    assert jobs.complete(
        job.job_key,
        worker_id="other-worker",
        allowed_status="finalizing",
    ) is None
    completed = jobs.complete(
        job.job_key,
        worker_id="contract-worker",
        allowed_status="finalizing",
    )
    assert completed is not None and completed.status == "completed"
    with case_store._session_factory.begin() as session:
        session.execute(delete(AnalysisJobRow).where(AnalysisJobRow.job_key == job.job_key))
        session.execute(delete(CaseRow).where(CaseRow.case_key == case.id))


class _QueueRedis:
    def __init__(self) -> None:
        self.queue: list[str] = []

    def set_review_queue(self, case_ids) -> None:
        self.queue = list(case_ids)


def test_postgres_analysis_job_service_completes_with_business_key() -> None:
    case_store = PostgresCaseStore(TEST_DATABASE_URL, connect_timeout_seconds=3)
    now = datetime.now(UTC)
    case = CaseRead(
        id=str(uuid4()),
        owner_id="contract-doctor",
        patient_age=42,
        patient_sex="F",
        complaint="PostgreSQL 完整分析任务契约测试",
        medical_history="",
        affected_eye="OS",
        consent_confirmed=True,
        status="analyzing",
        analysis=AnalysisService(Settings(model_mode="mock")).start(),
        created_at=now,
        updated_at=now,
    )
    case_store.save(case)
    jobs = PostgresAnalysisJobStore(case_store._session_factory)
    job = jobs.enqueue(case.id, max_attempts=2)
    service = AnalysisJobService(
        jobs,
        case_store,
        AnalysisService(Settings(model_mode="mock")),
        _QueueRedis(),
    )

    result = service.run_job(job.job_key)

    assert result.outcome == "completed"
    stored_job = jobs.get(job.job_key)
    assert stored_job is not None
    assert stored_job.status == "completed"
    assert stored_job.attempt_count == 1
    loaded_case = case_store.get(case.id)
    assert loaded_case is not None
    assert loaded_case.status == "awaiting_review"
    assert loaded_case.analysis is not None
    assert loaded_case.analysis.status == "completed"

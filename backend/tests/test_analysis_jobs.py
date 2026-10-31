from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from app.core.config import Settings
from app.db.analysis_jobs import MemoryAnalysisJobStore
from app.main import MemoryCaseStore
from app.schemas.case import CaseRead
from app.services.analysis import AnalysisService
from app.services.analysis_jobs import AnalysisJobService


class QueueOnlyRedis:
    def __init__(self) -> None:
        self.queue: list[str] = []

    def set_review_queue(self, case_ids) -> None:
        self.queue = list(case_ids)

    def add_review_queue(self, case_ids) -> None:
        for case_id in case_ids:
            value = str(case_id)
            if value not in self.queue:
                self.queue.append(value)

    def remove_review_queue(self, case_ids) -> None:
        removed = {str(case_id) for case_id in case_ids}
        self.queue = [case_id for case_id in self.queue if case_id not in removed]


class FailingAnalysisService:
    def start(self):
        raise AssertionError("start should use the case's queued analysis")

    def analyze(self, case, queued):
        raise RuntimeError("model runtime unavailable")


def make_case() -> CaseRead:
    now = datetime.now(UTC)
    return CaseRead(
        id=str(uuid4()),
        owner_id="doctor-1",
        owner_name="测试医生",
        patient_age=42,
        patient_sex="F",
        complaint="左眼视物模糊",
        medical_history="",
        affected_eye="OS",
        consent_confirmed=True,
        status="analyzing",
        analysis=AnalysisService(Settings(model_mode="mock")).start(),
        created_at=now,
        updated_at=now,
    )


def test_job_completes_case_and_marks_review_queue() -> None:
    jobs = MemoryAnalysisJobStore()
    cases = MemoryCaseStore()
    redis = QueueOnlyRedis()
    case = make_case()
    cases.save(case)
    service = AnalysisJobService(
        jobs,
        cases,
        AnalysisService(Settings(model_mode="mock")),
        redis,
    )
    job = jobs.enqueue(case.id)

    result = service.run_one()

    assert result is not None
    assert result.outcome == "completed"
    stored_case = cases.get(case.id)
    assert stored_case is not None
    assert stored_case.status == "awaiting_review"
    assert stored_case.analysis is not None
    assert stored_case.analysis.status == "completed"
    assert jobs.get(job.job_key).status == "completed"
    assert redis.queue == [case.id]
    assert job.id != job.job_key


def test_analysis_completion_updates_existing_queue_without_rebuilding_it() -> None:
    jobs = MemoryAnalysisJobStore()
    cases = MemoryCaseStore()
    redis = QueueOnlyRedis()
    existing_ids = [str(uuid4()) for _ in range(205)]
    redis.queue = existing_ids.copy()
    case = make_case()
    cases.save(case)
    job = jobs.enqueue(case.id)
    service = AnalysisJobService(
        jobs,
        cases,
        AnalysisService(Settings(model_mode="mock")),
        redis,
    )

    result = service.run_one()

    assert result is not None and result.outcome == "completed"
    assert len(redis.queue) == 206
    assert case.id in redis.queue
    assert redis.queue[:-1] == existing_ids
    assert jobs.get(job.job_key).status == "completed"


def test_latest_job_lookup_is_scoped_to_case() -> None:
    jobs = MemoryAnalysisJobStore()
    first_case_id = str(uuid4())
    second_case_id = str(uuid4())
    first = jobs.enqueue(first_case_id)
    jobs.enqueue(second_case_id)
    newest = jobs.enqueue(first_case_id)

    latest = jobs.get_latest_for_case(first_case_id)

    assert latest is not None
    assert latest.job_key == newest.job_key
    assert latest.job_key != first.job_key
    assert jobs.get_latest_for_case(str(uuid4())) is None


def test_retryable_failure_requeues_job() -> None:
    jobs = MemoryAnalysisJobStore()
    cases = MemoryCaseStore()
    case = make_case()
    cases.save(case)
    service = AnalysisJobService(
        jobs,
        cases,
        FailingAnalysisService(),
        QueueOnlyRedis(),
        max_attempts=2,
    )
    job = jobs.enqueue(case.id)

    result = service.run_one()

    assert result is not None and result.outcome == "failed"
    stored = jobs.get(job.job_key)
    assert stored is not None
    assert stored.status == "queued"
    assert stored.attempt_count == 1
    assert cases.get(case.id).status == "failed"


def test_expired_lease_is_recovered_after_worker_crash() -> None:
    jobs = MemoryAnalysisJobStore()
    case_id = str(uuid4())
    job = jobs.enqueue(case_id)
    claimed = jobs.claim(
        "worker-before-restart",
        now=datetime.now(UTC) - timedelta(minutes=10),
        lease_seconds=30,
    )
    assert claimed is not None
    recovered = jobs.recover_stale(now=datetime.now(UTC))
    assert recovered == 1
    recovered_job = jobs.claim(
        "worker-after-restart",
        now=datetime.now(UTC),
        lease_seconds=30,
    )
    assert recovered_job is not None
    assert recovered_job.job_key == job.job_key
    assert recovered_job.attempt_count == 2


def test_other_worker_cannot_run_without_its_lease() -> None:
    jobs = MemoryAnalysisJobStore()
    cases = MemoryCaseStore()
    case = make_case()
    cases.save(case)
    job = jobs.enqueue(case.id)
    claimed = jobs.claim(
        "worker-owner",
        now=datetime.now(UTC),
        lease_seconds=300,
    )
    assert claimed is not None and claimed.job_key == job.job_key
    service = AnalysisJobService(
        jobs,
        cases,
        AnalysisService(Settings(model_mode="mock")),
        QueueOnlyRedis(),
        worker_id="worker-intruder",
    )

    result = service.run_job(job.job_key)

    assert result.outcome == "not_claimed"
    assert cases.get(case.id).status == "analyzing"
    assert jobs.get(job.job_key).status == "running"
    assert jobs.get(job.job_key).attempt_count == 1


class ExplodingAnalysisService:
    def start(self):
        raise AssertionError("start should not be called")

    def analyze(self, case, queued):
        raise AssertionError("completed case analysis must not run again")


def test_completed_case_only_closes_job_without_reanalysis() -> None:
    jobs = MemoryAnalysisJobStore()
    cases = MemoryCaseStore()
    completed = make_case()
    completed.status = "awaiting_review"
    completed.analysis.status = "completed"
    completed.analysis.completed_at = datetime.now(UTC)
    cases.save(completed)
    job = jobs.enqueue(completed.id)
    service = AnalysisJobService(
        jobs,
        cases,
        ExplodingAnalysisService(),
        QueueOnlyRedis(),
    )

    result = service.run_one()

    assert result is not None and result.outcome == "already_completed"
    assert jobs.get(job.job_key).status == "completed"
    assert jobs.get(job.job_key).attempt_count == 1


def test_analysis_job_preserves_runtime_metadata() -> None:
    class RuntimeAnalysisService:
        def start(self):
            return AnalysisService(Settings(model_mode="mock")).start()

        def analyze(self, case, queued):
            result = AnalysisService(Settings(model_mode="mock")).analyze(
                case,
                queued,
            )
            return result.model_copy(
                update={
                    "runtime_metadata": {
                        "model": "Qwen3.5-4B",
                        "adapter_sha256": "b" * 64,
                        "peak_reserved_gib": 3.36,
                    }
                }
            )

    jobs = MemoryAnalysisJobStore()
    cases = MemoryCaseStore()
    case = make_case()
    cases.save(case)
    job = jobs.enqueue(case.id)
    service = AnalysisJobService(
        jobs,
        cases,
        RuntimeAnalysisService(),
        QueueOnlyRedis(),
    )

    result = service.run_one()

    assert result is not None and result.outcome == "completed"
    stored = cases.get(case.id)
    assert stored is not None
    assert stored.analysis is not None
    assert stored.analysis.runtime_metadata["model"] == "Qwen3.5-4B"
    assert stored.analysis.runtime_metadata["adapter_sha256"] == "b" * 64


def test_lease_renewal_requires_current_owner_and_unexpired_lease() -> None:
    jobs = MemoryAnalysisJobStore()
    job = jobs.enqueue(str(uuid4()))
    now = datetime.now(UTC)
    claimed = jobs.claim("worker-owner", now=now, lease_seconds=30)
    assert claimed is not None
    expires_before = claimed.lease_expires_at

    assert jobs.renew(
        job.job_key,
        "worker-other",
        now=now + timedelta(seconds=1),
        lease_seconds=30,
    ) is False
    assert jobs.renew(
        job.job_key,
        "worker-owner",
        now=now + timedelta(seconds=1),
        lease_seconds=30,
    ) is True
    assert jobs.get(job.job_key).lease_expires_at > expires_before


def test_worker_with_expired_lease_does_not_complete_or_write_case() -> None:
    jobs = MemoryAnalysisJobStore()
    cases = MemoryCaseStore()
    case = make_case()
    cases.save(case)
    job = jobs.enqueue(case.id)
    first = jobs.claim(
        "worker-old",
        now=datetime.now(UTC) - timedelta(minutes=10),
        lease_seconds=30,
    )
    assert first is not None
    second = jobs.claim(
        "worker-new",
        now=datetime.now(UTC),
        lease_seconds=30,
    )
    assert second is not None and second.lease_owner == "worker-new"

    assert jobs.complete(job.job_key, worker_id="worker-old") is None
    assert jobs.fail(
        job.job_key,
        "stale failure",
        retryable=False,
        worker_id="worker-old",
    ) is None
    stored_job = jobs.get(job.job_key)
    assert stored_job is not None
    assert stored_job.status == "running"
    assert stored_job.lease_owner == "worker-new"
    assert cases.get(case.id).status == "analyzing"


def test_finalize_is_fenced_to_current_worker() -> None:
    jobs = MemoryAnalysisJobStore()
    job = jobs.enqueue(str(uuid4()))
    claimed = jobs.claim(
        "worker-owner",
        now=datetime.now(UTC),
        lease_seconds=30,
    )
    assert claimed is not None

    assert jobs.begin_finalize(
        job.job_key,
        "worker-other",
        now=datetime.now(UTC),
    ) is None
    finalizing = jobs.begin_finalize(
        job.job_key,
        "worker-owner",
        now=datetime.now(UTC),
    )
    assert finalizing is not None and finalizing.status == "finalizing"
    assert jobs.claim(
        "worker-other",
        now=datetime.now(UTC),
        lease_seconds=30,
    ) is None
    completed = jobs.complete(
        job.job_key,
        worker_id="worker-owner",
        allowed_status="finalizing",
    )
    assert completed is not None and completed.status == "completed"


def test_service_renews_long_running_analysis_lease() -> None:
    jobs = MemoryAnalysisJobStore()
    cases = MemoryCaseStore()
    case = make_case()
    cases.save(case)
    job = jobs.enqueue(case.id)
    claimed = jobs.claim(
        "worker-slow",
        now=datetime.now(UTC),
        lease_seconds=3,
    )
    assert claimed is not None
    service = AnalysisJobService(
        jobs,
        cases,
        AnalysisService(Settings(model_mode="mock")),
        QueueOnlyRedis(),
        lease_seconds=3,
        worker_id="worker-slow",
    )
    original_renew = jobs.renew
    renewal_count = 0

    def renew(*args, **kwargs):
        nonlocal renewal_count
        renewal_count += 1
        return original_renew(*args, **kwargs)

    jobs.renew = renew
    original_analyze = service.analysis_service.analyze

    def slow_analyze(case, queued):
        import time

        time.sleep(4.0)
        return original_analyze(case, queued)

    service.analysis_service = type(
        "SlowAnalysisService",
        (),
        {
            "start": lambda self: AnalysisService(
                Settings(model_mode="mock")
            ).start(),
            "analyze": lambda self, case, queued: slow_analyze(case, queued),
        },
    )()

    result = service.run_job(job.job_key)

    assert result.outcome == "completed"
    assert renewal_count >= 1
    assert jobs.get(job.job_key).status == "completed"

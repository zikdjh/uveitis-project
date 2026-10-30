from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from app.schemas.case import AnalysisResult, CaseRead


@dataclass(frozen=True)
class JobRunResult:
    job_id: str
    case_id: str
    outcome: str
    error: str = ""


class AnalysisJobService:
    """Durable analysis dispatch shared by the API, worker and recovery scan."""

    def __init__(
        self,
        job_store,
        case_store,
        analysis_service,
        redis_store,
        *,
        lease_seconds: int = 300,
        max_attempts: int = 2,
        worker_id: str | None = None,
    ) -> None:
        self.job_store = job_store
        self.case_store = case_store
        self.analysis_service = analysis_service
        self.redis_store = redis_store
        self.lease_seconds = max(3, lease_seconds)
        self.max_attempts = max(1, max_attempts)
        self.worker_id = worker_id or f"web-{uuid4().hex[:12]}"

    def enqueue(self, case_id: str):
        return self.job_store.enqueue(case_id, max_attempts=self.max_attempts)

    def get_latest_for_case(self, case_id: str):
        return self.job_store.get_latest_for_case(case_id)

    def list_recent(self, *, limit: int = 50):
        return self.job_store.list_recent(limit=limit)

    def run_job(self, job_id: str) -> JobRunResult:
        job = self.job_store.get(job_id)
        if job is None:
            return JobRunResult(job_id, "", "missing")
        if job.status == "completed":
            return JobRunResult(job_id, job.case_id, "already_completed")
        if job.status not in {"queued", "running"}:
            return JobRunResult(job_id, job.case_id, "not_claimed")
        if job.status == "queued":
            claimed = self.job_store.claim(
                self.worker_id,
                now=datetime.now(UTC),
                lease_seconds=self.lease_seconds,
                job_key=job.job_key,
            )
            if claimed is None or claimed.job_key != job.job_key:
                return JobRunResult(job_id, job.case_id, "not_claimed")
            job = claimed
        now = datetime.now(UTC)
        if (
            job.lease_owner != self.worker_id
            or job.lease_expires_at is None
            or job.lease_expires_at <= now
        ):
            return JobRunResult(job_id, job.case_id, "not_claimed")
        case = self.case_store.get(job.case_id)
        if case is None:
            self._fail_owned(
                job.job_key,
                "病例已不存在",
                retryable=False,
            )
            return JobRunResult(job.job_key, job.case_id, "failed", "病例已不存在")
        return self._execute(job, case)

    def run_one(self) -> JobRunResult | None:
        job = self.job_store.claim(
            self.worker_id,
            now=datetime.now(UTC),
            lease_seconds=self.lease_seconds,
        )
        if job is None:
            return None
        case = self.case_store.get(job.case_id)
        if case is None:
            self._fail_owned(job.job_key, "病例已不存在", retryable=False)
            return JobRunResult(job.job_key, job.case_id, "failed", "病例已不存在")
        return self._execute(job, case)

    def recover_stale(self) -> int:
        return self.job_store.recover_stale(
            now=datetime.now(UTC),
            max_attempts=self.max_attempts,
        )

    def _execute(self, job, case: CaseRead) -> JobRunResult:
        if (
            case.status in {"awaiting_review", "reviewed"}
            and case.analysis is not None
            and case.analysis.status == "completed"
        ):
            if self.job_store.complete(
                job.job_key,
                worker_id=self.worker_id,
            ) is None:
                return JobRunResult(job.job_key, job.case_id, "lease_lost")
            self._sync_review_queue()
            return JobRunResult(job.job_key, job.case_id, "already_completed")
        queued = case.analysis or self.analysis_service.start()
        result, failure = self._analyze_with_lease(job, case, queued)
        if result is None and failure is None:
            return JobRunResult(
                job.job_key,
                job.case_id,
                "lease_lost",
                "分析期间任务租约已转移",
            )
        if failure is not None:
            error = f"{type(failure).__name__}: {failure}"[:2000]
            if not self._still_owned(job.job_key):
                return JobRunResult(job.job_key, job.case_id, "lease_lost", error)
            if self.job_store.begin_finalize(
                job.job_key,
                self.worker_id,
                now=datetime.now(UTC),
            ) is None:
                return JobRunResult(job.job_key, job.case_id, "lease_lost", error)
            self._mark_case_failed(case, queued, error)
            if self._fail_owned(
                job.job_key,
                error,
                retryable=True,
                allowed_status="finalizing",
            ) is None:
                return JobRunResult(job.job_key, job.case_id, "lease_lost", error)
            return JobRunResult(job.job_key, job.case_id, "failed", error)
        assert result is not None
        if not self._still_owned(job.job_key):
            return JobRunResult(job.job_key, job.case_id, "lease_lost")
        if self.job_store.begin_finalize(
            job.job_key,
            self.worker_id,
            now=datetime.now(UTC),
        ) is None:
            return JobRunResult(job.job_key, job.case_id, "lease_lost")
        self._mark_case_completed(case, result)
        if self.job_store.complete(
            job.job_key,
            worker_id=self.worker_id,
            allowed_status="finalizing",
        ) is None:
            return JobRunResult(job.job_key, job.case_id, "lease_lost")
        self._sync_review_queue()
        return JobRunResult(job.job_key, job.case_id, "completed")

    def _analyze_with_lease(
        self,
        job,
        case: CaseRead,
        queued: AnalysisResult,
    ) -> tuple[AnalysisResult | None, Exception | None]:
        """Run inference while the worker thread renews its lease."""
        result: AnalysisResult | None = None
        failure: Exception | None = None
        done = threading.Event()
        interval = min(30.0, max(0.5, self.lease_seconds / 3))

        def analyze() -> None:
            nonlocal result, failure
            try:
                try:
                    result = self.analysis_service.analyze(case, queued)
                except Exception as exc:
                    failure = exc
            finally:
                done.set()

        inference = threading.Thread(
            target=analyze,
            name=f"analysis-inference-{job.job_key[:8]}",
            daemon=True,
        )
        inference.start()
        next_renewal = time.monotonic() + interval
        while not done.wait(0.25):
            if time.monotonic() < next_renewal:
                continue
            if not self.job_store.renew(
                job.job_key,
                self.worker_id,
                now=datetime.now(UTC),
                lease_seconds=self.lease_seconds,
            ):
                return None, None
            next_renewal = time.monotonic() + interval
        inference.join(timeout=interval)
        if not self._still_owned(job.job_key):
            return None, None
        return result, failure

    def _still_owned(self, job_id: str) -> bool:
        job = self.job_store.get(job_id)
        return bool(
            job is not None
            and job.status in {"running", "finalizing"}
            and job.lease_owner == self.worker_id
            and job.lease_expires_at is not None
            and job.lease_expires_at > datetime.now(UTC)
        )

    def _fail_owned(
        self,
        job_id: str,
        error: str,
        *,
        retryable: bool,
        allowed_status: str = "running",
    ):
        return self.job_store.fail(
            job_id,
            error,
            retryable=retryable,
            worker_id=self.worker_id,
            allowed_status=allowed_status,
        )

    def _mark_case_completed(self, case: CaseRead, result: AnalysisResult) -> None:
        case.status = "awaiting_review"
        case.analysis = result
        case.updated_at = datetime.now(UTC)
        self.case_store.save(case)

    def _mark_case_failed(
        self,
        case: CaseRead,
        queued: AnalysisResult,
        error: str,
    ) -> None:
        failed = queued.model_copy(
            update={
                "status": "failed",
                "completed_at": datetime.now(UTC),
                "error": error,
                "safety_flags": ["分析任务失败", "必须人工复核"],
            }
        )
        case.status = "failed"
        case.analysis = failed
        case.updated_at = datetime.now(UTC)
        self.case_store.save(case)

    def _sync_review_queue(self) -> None:
        cases = self.case_store.list(status="awaiting_review", limit=10_000)
        self.redis_store.set_review_queue(
            case.id for case in cases
        )

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol
from uuid import uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import AnalysisJobRow


JobStatus = Literal["queued", "running", "finalizing", "completed", "failed"]


class AnalysisJob(Protocol):
    id: int
    job_key: str
    case_id: str
    status: JobStatus
    attempt_count: int
    max_attempts: int
    error: str
    lease_owner: str
    lease_expires_at: datetime | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class AnalysisJobStore(Protocol):
    def enqueue(
        self,
        case_id: str,
        *,
        max_attempts: int = 2,
    ) -> AnalysisJob: ...

    def get(self, job_id: str) -> AnalysisJob | None: ...

    def get_latest_for_case(self, case_id: str) -> AnalysisJob | None: ...

    def claim(
        self,
        worker_id: str,
        *,
        now: datetime,
        lease_seconds: int,
        job_key: str | None = None,
    ) -> AnalysisJob | None: ...

    def renew(
        self,
        job_id: str,
        worker_id: str,
        *,
        now: datetime,
        lease_seconds: int,
    ) -> bool: ...

    def begin_finalize(
        self,
        job_id: str,
        worker_id: str,
        *,
        now: datetime,
    ) -> AnalysisJob | None: ...

    def complete(
        self,
        job_id: str,
        *,
        worker_id: str | None = None,
        allowed_status: JobStatus = "running",
        now: datetime | None = None,
    ) -> AnalysisJob | None: ...

    def fail(
        self,
        job_id: str,
        error: str,
        *,
        retryable: bool,
        worker_id: str | None = None,
        allowed_status: JobStatus = "running",
        now: datetime | None = None,
    ) -> AnalysisJob | None: ...

    def recover_stale(self, *, now: datetime, max_attempts: int = 2) -> int: ...


class PostgresAnalysisJobStore:
    """PostgreSQL-backed analysis queue with short worker leases."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def enqueue(
        self,
        case_id: str,
        *,
        max_attempts: int = 2,
    ) -> AnalysisJobRow:
        now = datetime.now(UTC)
        with self._session_factory.begin() as session:
            row = AnalysisJobRow(
                job_key=str(uuid4()),
                case_id=case_id,
                status="queued",
                attempt_count=0,
                max_attempts=max(1, max_attempts),
                lease_owner="",
                lease_expires_at=None,
                error="",
                created_at=now,
                updated_at=now,
                started_at=None,
                completed_at=None,
            )
            session.add(row)
            session.flush()
            return row

    def get(self, job_id: str) -> AnalysisJobRow | None:
        with self._session_factory() as session:
            return session.scalar(
                select(AnalysisJobRow).where(AnalysisJobRow.job_key == job_id)
            )

    def get_latest_for_case(self, case_id: str) -> AnalysisJobRow | None:
        with self._session_factory() as session:
            return session.scalar(
                select(AnalysisJobRow)
                .where(AnalysisJobRow.case_id == case_id)
                .order_by(
                    AnalysisJobRow.created_at.desc(),
                    AnalysisJobRow.id.desc(),
                )
                .limit(1)
            )

    def claim(
        self,
        worker_id: str,
        *,
        now: datetime,
        lease_seconds: int,
        job_key: str | None = None,
    ) -> AnalysisJobRow | None:
        claimable = or_(
            (
                (AnalysisJobRow.status == "queued")
                & (AnalysisJobRow.attempt_count < AnalysisJobRow.max_attempts)
            ),
            (
                AnalysisJobRow.status.in_(("running", "finalizing"))
                & (AnalysisJobRow.lease_expires_at < now)
                & (AnalysisJobRow.attempt_count < AnalysisJobRow.max_attempts)
            ),
        )
        if job_key is not None:
            claimable = claimable & (AnalysisJobRow.job_key == job_key)
        with self._session_factory.begin() as session:
            row = session.scalar(
                select(AnalysisJobRow)
                .where(claimable)
                .order_by(AnalysisJobRow.created_at.asc())
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if row is None:
                return None
            row.status = "running"
            row.attempt_count += 1
            row.lease_owner = worker_id
            row.lease_expires_at = now + timedelta(seconds=lease_seconds)
            row.started_at = row.started_at or now
            row.updated_at = now
            row.error = ""
            return row

    def complete(
        self,
        job_id: str,
        *,
        worker_id: str | None = None,
        allowed_status: JobStatus = "running",
        now: datetime | None = None,
    ) -> AnalysisJobRow | None:
        now = now or datetime.now(UTC)
        if worker_id is not None:
            result = self._finish_owned(
                job_id,
                worker_id=worker_id,
                status="completed",
                now=now,
                allowed_status=allowed_status,
            )
            return self.get(job_id) if result is not None else None
        with self._session_factory.begin() as session:
            row = self._locked(session, job_id)
            row.status = "completed"
            row.completed_at = now
            row.updated_at = now
            row.error = ""
            row.lease_owner = ""
            row.lease_expires_at = None
            return row

    def fail(
        self,
        job_id: str,
        error: str,
        *,
        retryable: bool,
        worker_id: str | None = None,
        allowed_status: JobStatus = "running",
        now: datetime | None = None,
    ) -> AnalysisJobRow | None:
        now = now or datetime.now(UTC)
        if worker_id is not None:
            result = self._finish_owned(
                job_id,
                worker_id=worker_id,
                status="queued" if retryable else "failed",
                now=now,
                error=error,
                retryable=retryable,
                allowed_status=allowed_status,
            )
            return self.get(job_id) if result is not None else None
        with self._session_factory.begin() as session:
            row = self._locked(session, job_id)
            row.error = error[:2000]
            row.updated_at = now
            row.lease_owner = ""
            row.lease_expires_at = None
            if retryable and row.attempt_count < row.max_attempts:
                row.status = "queued"
            else:
                row.status = "failed"
                row.completed_at = now
            return row

    def renew(
        self,
        job_id: str,
        worker_id: str,
        *,
        now: datetime,
        lease_seconds: int,
    ) -> bool:
        """Extend only an unexpired lease still owned by the worker."""
        with self._session_factory.begin() as session:
            result = session.execute(
                update(AnalysisJobRow)
                .where(
                    AnalysisJobRow.job_key == job_id,
                    AnalysisJobRow.status == "running",
                    AnalysisJobRow.lease_owner == worker_id,
                    AnalysisJobRow.lease_expires_at > now,
                )
                .values(
                    lease_expires_at=now + timedelta(seconds=lease_seconds),
                    updated_at=now,
                )
            )
            return result.rowcount == 1

    def begin_finalize(
        self,
        job_id: str,
        worker_id: str,
        *,
        now: datetime,
    ) -> AnalysisJobRow | None:
        """Fence the job so only this worker may write the final case state."""
        with self._session_factory.begin() as session:
            result = session.execute(
                update(AnalysisJobRow)
                .where(
                    AnalysisJobRow.job_key == job_id,
                    AnalysisJobRow.status == "running",
                    AnalysisJobRow.lease_owner == worker_id,
                    AnalysisJobRow.lease_expires_at > now,
                )
                .values(status="finalizing", updated_at=now)
            )
            updated = result.rowcount == 1
        return self.get(job_id) if updated else None

    def recover_stale(self, *, now: datetime, max_attempts: int = 2) -> int:
        """Return abandoned leases to the queue, or fail them after the cap."""
        with self._session_factory.begin() as session:
            stale = select(AnalysisJobRow).where(
                AnalysisJobRow.status.in_(("running", "finalizing")),
                AnalysisJobRow.lease_expires_at < now,
            ).with_for_update(skip_locked=True)
            rows = session.scalars(stale).all()
            for row in rows:
                row.error = "worker lease expired before completion"
                row.updated_at = now
                row.lease_owner = ""
                row.lease_expires_at = None
                if row.attempt_count < min(row.max_attempts, max_attempts):
                    row.status = "queued"
                else:
                    row.status = "failed"
                    row.completed_at = now
            return len(rows)

    @staticmethod
    def _locked(session: Session, job_id: str) -> AnalysisJobRow:
        row = session.scalar(
            select(AnalysisJobRow)
            .where(AnalysisJobRow.job_key == job_id)
            .with_for_update()
        )
        if row is None:
            raise LookupError(f"analysis job not found: {job_id}")
        return row

    def _finish_owned(
        self,
        job_id: str,
        *,
        worker_id: str,
        status: JobStatus,
        now: datetime,
        error: str = "",
        retryable: bool = False,
        allowed_status: JobStatus = "running",
    ) -> int | None:
        with self._session_factory.begin() as session:
            query = session.query(AnalysisJobRow).filter(
                AnalysisJobRow.job_key == job_id,
                AnalysisJobRow.status == allowed_status,
                AnalysisJobRow.lease_owner == worker_id,
            )
            if allowed_status == "running":
                query = query.filter(AnalysisJobRow.lease_expires_at > now)
            row = query.with_for_update().one_or_none()
            if row is None:
                return None
            row.error = error[:2000]
            row.updated_at = now
            row.lease_owner = ""
            row.lease_expires_at = None
            if status == "completed":
                row.status = "completed"
                row.completed_at = now
            elif status == "queued" and retryable and row.attempt_count < row.max_attempts:
                row.status = "queued"
            else:
                row.status = "failed"
                row.completed_at = now
            return row.id


class MemoryAnalysisJobStore:
    """In-process queue used by isolated tests and local fallback development."""

    def __init__(self) -> None:
        self._jobs: dict[str, dict] = {}
        self._next_id = 1

    def enqueue(self, case_id: str, *, max_attempts: int = 2):
        now = datetime.now(UTC)
        job = {
            "id": self._next_id,
            "job_key": str(uuid4()),
            "case_id": case_id,
            "status": "queued",
            "attempt_count": 0,
            "max_attempts": max(1, max_attempts),
            "lease_owner": "",
            "lease_expires_at": None,
            "error": "",
            "created_at": now,
            "updated_at": now,
            "started_at": None,
            "completed_at": None,
        }
        self._next_id += 1
        self._jobs[job["job_key"]] = job
        return _MemoryJob(job)

    def get(self, job_id: str):
        job = self._jobs.get(job_id)
        return _MemoryJob(job) if job else None

    def get_latest_for_case(self, case_id: str):
        jobs = [
            job
            for job in self._jobs.values()
            if job["case_id"] == case_id
        ]
        if not jobs:
            return None
        latest = max(jobs, key=lambda item: (item["created_at"], item["id"]))
        return _MemoryJob(latest)

    def claim(
        self,
        worker_id: str,
        *,
        now: datetime,
        lease_seconds: int,
        job_key: str | None = None,
    ):
        for job in sorted(self._jobs.values(), key=lambda item: item["created_at"]):
            if job_key is not None and job["job_key"] != job_key:
                continue
            stale = (
                job["status"] in {"running", "finalizing"}
                and job["lease_expires_at"] is not None
                and job["lease_expires_at"] < now
            )
            if job["status"] != "queued" and not stale:
                continue
            if job["attempt_count"] >= job["max_attempts"]:
                continue
            job["status"] = "running"
            job["attempt_count"] += 1
            job["lease_owner"] = worker_id
            job["lease_expires_at"] = now + timedelta(seconds=lease_seconds)
            job["started_at"] = job["started_at"] or now
            job["updated_at"] = now
            job["error"] = ""
            return _MemoryJob(job)
        return None

    def renew(
        self,
        job_id: str,
        worker_id: str,
        *,
        now: datetime,
        lease_seconds: int,
    ) -> bool:
        job = self._jobs.get(job_id)
        if (
            job is None
            or job["status"] != "running"
            or job["lease_owner"] != worker_id
            or job["lease_expires_at"] is None
            or job["lease_expires_at"] <= now
        ):
            return False
        job["lease_expires_at"] = now + timedelta(seconds=lease_seconds)
        job["updated_at"] = now
        return True

    def complete(
        self,
        job_id: str,
        *,
        worker_id: str | None = None,
        allowed_status: JobStatus = "running",
        now: datetime | None = None,
    ):
        now = now or datetime.now(UTC)
        job = self._get(job_id)
        if (
            worker_id is not None
            and (
                job["status"] != allowed_status
                or job["lease_owner"] != worker_id
            )
        ):
            return None
        job.update(status="completed", completed_at=now, updated_at=now, error="", lease_owner="", lease_expires_at=None)
        return _MemoryJob(job)

    def fail(
        self,
        job_id: str,
        error: str,
        *,
        retryable: bool,
        worker_id: str | None = None,
        allowed_status: JobStatus = "running",
        now: datetime | None = None,
    ):
        now = now or datetime.now(UTC)
        job = self._get(job_id)
        if (
            worker_id is not None
            and (
                job["status"] != allowed_status
                or job["lease_owner"] != worker_id
            )
        ):
            return None
        job.update(error=error[:2000], updated_at=now, lease_owner="", lease_expires_at=None)
        if retryable and job["attempt_count"] < job["max_attempts"]:
            job["status"] = "queued"
        else:
            job.update(status="failed", completed_at=now)
        return _MemoryJob(job)

    def begin_finalize(
        self,
        job_id: str,
        worker_id: str,
        *,
        now: datetime,
    ):
        job = self._jobs.get(job_id)
        if (
            job is None
            or job["status"] != "running"
            or job["lease_owner"] != worker_id
            or job["lease_expires_at"] is None
            or job["lease_expires_at"] <= now
        ):
            return None
        job["status"] = "finalizing"
        job["updated_at"] = now
        return _MemoryJob(job)

    def recover_stale(self, *, now: datetime, max_attempts: int = 2) -> int:
        recovered = 0
        for job in self._jobs.values():
            if job["status"] not in {"running", "finalizing"} or not job["lease_expires_at"] or job["lease_expires_at"] >= now:
                continue
            job.update(error="worker lease expired before completion", updated_at=now, lease_owner="", lease_expires_at=None)
            if job["attempt_count"] < min(job["max_attempts"], max_attempts):
                job["status"] = "queued"
            else:
                job.update(status="failed", completed_at=now)
            recovered += 1
        return recovered

    def _get(self, job_id: str) -> dict:
        job = self._jobs.get(job_id)
        if job is None:
            raise LookupError(f"analysis job not found: {job_id}")
        return job


class _MemoryJob:
    def __init__(self, job: dict) -> None:
        self._job = job

    def __getattr__(self, name: str):
        try:
            return self._job[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

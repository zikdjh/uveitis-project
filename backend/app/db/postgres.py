from __future__ import annotations

import json
from typing import Protocol

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base, CaseRow
from app.schemas.case import CaseRead, CaseStats


class CaseRepository(Protocol):
    def save(self, case: CaseRead) -> CaseRead: ...

    def get(self, case_id: str) -> CaseRead | None: ...

    def list(self, limit: int = 100) -> list[CaseRead]: ...

    def stats(self) -> CaseStats: ...


class PostgresCaseStore:
    """PostgreSQL case repository with validated JSON payload snapshots."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self.engine: Engine = create_engine(database_url, pool_pre_ping=True)
        self._session_factory = sessionmaker(
            bind=self.engine,
            class_=Session,
            expire_on_commit=False,
        )
        Base.metadata.create_all(self.engine)

    def save(self, case: CaseRead) -> CaseRead:
        with self._session_factory.begin() as session:
            row = session.get(CaseRow, case.id)
            if row is None:
                session.add(
                    CaseRow(
                        id=case.id,
                        status=case.status,
                        created_at=case.created_at,
                        updated_at=case.updated_at,
                        payload_json=case.model_dump_json(),
                    )
                )
            else:
                row.status = case.status
                row.updated_at = case.updated_at
                row.payload_json = case.model_dump_json()
        return case

    def get(self, case_id: str) -> CaseRead | None:
        with self._session_factory() as session:
            row = session.get(CaseRow, case_id)
        return self._decode(row.payload_json) if row else None

    def list(self, limit: int = 100) -> list[CaseRead]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(CaseRow).order_by(CaseRow.updated_at.desc()).limit(limit)
            ).all()
        return [self._decode(row.payload_json) for row in rows]

    def stats(self) -> CaseStats:
        with self._session_factory() as session:
            rows = session.execute(
                select(CaseRow.status, func.count()).group_by(CaseRow.status)
            ).all()
        counts = {status: count for status, count in rows}
        return CaseStats(
            total=sum(counts.values()),
            analyzing=counts.get("analyzing", 0),
            awaiting_review=counts.get("awaiting_review", 0),
            reviewed=counts.get("reviewed", 0),
        )

    def ping(self) -> bool:
        with self.engine.connect() as connection:
            return connection.execute(text("SELECT 1")).scalar_one() == 1

    @staticmethod
    def _decode(payload: str) -> CaseRead:
        return CaseRead.model_validate(json.loads(payload))

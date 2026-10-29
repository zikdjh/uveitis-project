from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import or_

from app.db.models import AuthAuditRow
from app.schemas.auth import AuthAuditEventRead


class AuthAuditStore:
    """SQLAlchemy-backed authentication and authorization audit trail."""

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def record(
        self,
        *,
        event: str,
        outcome: str,
        username: str,
        user_id: str | None,
        actor_id: str | None,
        ip_address: str,
        user_agent: str,
        detail: str = "",
    ) -> AuthAuditEventRead:
        row = AuthAuditRow(
            event_key=str(uuid4()),
            event=event,
            outcome=outcome,
            username=username.strip().lower(),
            user_id=user_id,
            actor_id=actor_id,
            ip_address=ip_address[:64],
            user_agent=user_agent[:500],
            detail=detail,
            created_at=datetime.now(UTC),
        )
        with self._session_factory.begin() as session:
            session.add(row)
        return self._from_row(row)

    @staticmethod
    def _query(
        session,
        *,
        event: str | None = None,
        outcome: str | None = None,
        from_at: datetime | None = None,
        to_at: datetime | None = None,
        search: str | None = None,
    ):
        query = session.query(AuthAuditRow)
        if event:
            query = query.where(AuthAuditRow.event == event)
        if outcome:
            query = query.where(AuthAuditRow.outcome == outcome)
        if from_at is not None:
            query = query.where(AuthAuditRow.created_at >= from_at)
        if to_at is not None:
            query = query.where(AuthAuditRow.created_at < to_at)
        if search and search.strip():
            pattern = f"%{search.strip()}%"
            query = query.where(
                or_(
                    AuthAuditRow.username.ilike(pattern),
                    AuthAuditRow.detail.ilike(pattern),
                )
            )
        return query

    def list_page(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        event: str | None = None,
        outcome: str | None = None,
        from_at: datetime | None = None,
        to_at: datetime | None = None,
        search: str | None = None,
    ) -> tuple[list[AuthAuditEventRead], int]:
        with self._session_factory() as session:
            query = self._query(
                session,
                event=event,
                outcome=outcome,
                from_at=from_at,
                to_at=to_at,
                search=search,
            )
            total = query.count()
            rows = (
                query.order_by(
                    AuthAuditRow.created_at.desc(),
                    AuthAuditRow.id.desc(),
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )
        return [self._from_row(row) for row in rows], total

    def list(self, limit: int = 100) -> list[AuthAuditEventRead]:
        with self._session_factory() as session:
            rows = session.query(AuthAuditRow).order_by(
                AuthAuditRow.created_at.desc()
            ).limit(limit).all()
        return [self._from_row(row) for row in rows]

    @staticmethod
    def _from_row(row: AuthAuditRow) -> AuthAuditEventRead:
        return AuthAuditEventRead(
            id=row.event_key,
            event=row.event,
            outcome=row.outcome,
            username=row.username,
            user_id=row.user_id,
            actor_id=row.actor_id,
            ip_address=row.ip_address,
            user_agent=row.user_agent,
            detail=row.detail,
            created_at=row.created_at,
        )


class MemoryAuthAuditStore:
    """In-process audit trail used by isolated tests."""

    def __init__(self) -> None:
        self.events: list[AuthAuditEventRead] = []

    def record(self, **values) -> AuthAuditEventRead:
        event = AuthAuditEventRead(
            id=str(uuid4()),
            event=values["event"],
            outcome=values["outcome"],
            username=values["username"].strip().lower(),
            user_id=values.get("user_id"),
            actor_id=values.get("actor_id"),
            ip_address=values.get("ip_address", "")[:64],
            user_agent=values.get("user_agent", "")[:500],
            detail=values.get("detail", ""),
            created_at=datetime.now(UTC),
        )
        self.events.insert(0, event)
        return event

    def list_page(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        event: str | None = None,
        outcome: str | None = None,
        from_at: datetime | None = None,
        to_at: datetime | None = None,
        search: str | None = None,
    ) -> tuple[list[AuthAuditEventRead], int]:
        values = self.events
        if event:
            values = [item for item in values if item.event == event]
        if outcome:
            values = [item for item in values if item.outcome == outcome]
        if from_at is not None:
            values = [item for item in values if item.created_at >= from_at]
        if to_at is not None:
            values = [item for item in values if item.created_at < to_at]
        if search and search.strip():
            needle = search.strip().lower()
            values = [
                item
                for item in values
                if needle in item.username.lower() or needle in item.detail.lower()
            ]
        offset = (page - 1) * page_size
        return values[offset : offset + page_size], len(values)

    def list(self, limit: int = 100) -> list[AuthAuditEventRead]:
        return self.events[:limit]

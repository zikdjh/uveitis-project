from __future__ import annotations

from datetime import UTC, datetime

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

    def list(self, limit: int = 100) -> list[AuthAuditEventRead]:
        with self._session_factory() as session:
            rows = session.query(AuthAuditRow).order_by(
                AuthAuditRow.created_at.desc()
            ).limit(limit).all()
        return [self._from_row(row) for row in rows]

    @staticmethod
    def _from_row(row: AuthAuditRow) -> AuthAuditEventRead:
        return AuthAuditEventRead(
            id=row.id,
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
            id=len(self.events) + 1,
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

    def list(self, limit: int = 100) -> list[AuthAuditEventRead]:
        return self.events[:limit]

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

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


class SQLiteAuthAuditStore:
    """SQLite audit trail used when the application falls back to local storage."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS auth_audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    username TEXT NOT NULL,
                    user_id TEXT,
                    actor_id TEXT,
                    ip_address TEXT NOT NULL,
                    user_agent TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_auth_audit_created_at "
                "ON auth_audit_events(created_at DESC)"
            )

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
        created_at = datetime.now(UTC)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO auth_audit_events
                (event, outcome, username, user_id, actor_id, ip_address,
                 user_agent, detail, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event,
                    outcome,
                    username.strip().lower(),
                    user_id,
                    actor_id,
                    ip_address[:64],
                    user_agent[:500],
                    detail,
                    created_at.isoformat(),
                ),
            )
            event_id = int(cursor.lastrowid)
        return AuthAuditEventRead(
            id=event_id,
            event=event,
            outcome=outcome,
            username=username.strip().lower(),
            user_id=user_id,
            actor_id=actor_id,
            ip_address=ip_address[:64],
            user_agent=user_agent[:500],
            detail=detail,
            created_at=created_at,
        )

    def list(self, limit: int = 100) -> list[AuthAuditEventRead]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM auth_audit_events ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    @staticmethod
    def _from_row(row: sqlite3.Row) -> AuthAuditEventRead:
        created_at = datetime.fromisoformat(str(row["created_at"]))
        return AuthAuditEventRead(
            id=int(row["id"]),
            event=str(row["event"]),
            outcome=str(row["outcome"]),
            username=str(row["username"]),
            user_id=str(row["user_id"]) if row["user_id"] else None,
            actor_id=str(row["actor_id"]) if row["actor_id"] else None,
            ip_address=str(row["ip_address"]),
            user_agent=str(row["user_agent"]),
            detail=str(row["detail"]),
            created_at=created_at,
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

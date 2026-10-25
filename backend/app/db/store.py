import json
import sqlite3
from pathlib import Path

from app.schemas.case import CaseRead, CaseStats


class CaseStore:
    """Small SQLite adapter; case payloads are stored as validated JSON snapshots."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS cases (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_cases_updated_at ON cases(updated_at DESC)"
            )

    def save(self, case: CaseRead) -> CaseRead:
        payload = case.model_dump_json()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO cases (id, status, created_at, updated_at, payload_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    updated_at = excluded.updated_at,
                    payload_json = excluded.payload_json
                """,
                (
                    case.id,
                    case.status,
                    case.created_at.isoformat(),
                    case.updated_at.isoformat(),
                    payload,
                ),
            )
        return case

    def get(self, case_id: str) -> CaseRead | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM cases WHERE id = ?", (case_id,)
            ).fetchone()
        return self._decode(row["payload_json"]) if row else None

    def list(self, limit: int = 100) -> list[CaseRead]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM cases ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._decode(row["payload_json"]) for row in rows]

    def stats(self) -> CaseStats:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT status, COUNT(*) AS count FROM cases GROUP BY status"
            ).fetchall()
        counts = {row["status"]: row["count"] for row in rows}
        return CaseStats(
            total=sum(counts.values()),
            analyzing=counts.get("analyzing", 0),
            awaiting_review=counts.get("awaiting_review", 0),
            reviewed=counts.get("reviewed", 0),
        )

    @staticmethod
    def _decode(payload: str) -> CaseRead:
        return CaseRead.model_validate(json.loads(payload))

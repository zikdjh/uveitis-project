from __future__ import annotations

import json
from datetime import datetime
from typing import Protocol
from uuid import uuid4

from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base, CaseRow
from app.db.naming import (
    BUSINESS_KEY_COLUMNS,
    LEGACY_COLUMN_RENAMES,
    LEGACY_TABLE_RENAMES,
    PRIMARY_KEY_COLUMN,
)
from app.schemas.case import CaseRead, CaseStats


class CaseRepository(Protocol):
    def save(self, case: CaseRead) -> CaseRead: ...

    def get(self, case_id: str) -> CaseRead | None: ...

    def list(
        self,
        *,
        owner_id: str | None = None,
        status: str | None = None,
        from_at: datetime | None = None,
        to_at: datetime | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[CaseRead]: ...

    def count(
        self,
        *,
        owner_id: str | None = None,
        status: str | None = None,
        from_at: datetime | None = None,
        to_at: datetime | None = None,
    ) -> int: ...

    def stats(self) -> CaseStats: ...


def migrate_database_identifiers(engine: Engine) -> None:
    """Rename legacy identifiers and split business keys from identity keys."""
    _rename_legacy_identifiers(engine)
    _migrate_primary_keys(engine)
    _ensure_case_ownership(engine)


def _ensure_case_ownership(engine: Engine) -> None:
    """Add owner scoping to existing case tables without rewriting payloads."""
    table = "t_case"
    if table not in inspect(engine).get_table_names():
        return
    owner_column = "f_owner_id"
    columns = _column_map(engine, table)
    if owner_column not in columns:
        with engine.begin() as connection:
            connection.execute(
                text(
                    f'ALTER TABLE "{table}" ADD COLUMN "{owner_column}" '
                    "VARCHAR(36) NOT NULL DEFAULT ''"
                )
            )
    indexes = {index.get("name") for index in inspect(engine).get_indexes(table)}
    if "ix_t_case_f_owner_id" not in indexes:
        with engine.begin() as connection:
            connection.execute(
                text(
                    f'CREATE INDEX "ix_t_case_f_owner_id" '
                    f'ON "{table}" ("{owner_column}")'
                )
            )


def _rename_legacy_identifiers(engine: Engine) -> None:
    table_names = set(inspect(engine).get_table_names())
    with engine.begin() as connection:
        for legacy_name, current_name in LEGACY_TABLE_RENAMES.items():
            if legacy_name not in table_names or current_name in table_names:
                continue
            connection.execute(
                text(f'ALTER TABLE "{legacy_name}" RENAME TO "{current_name}"')
            )
            table_names.remove(legacy_name)
            table_names.add(current_name)

    for table, column_mapping in LEGACY_COLUMN_RENAMES.items():
        if table not in table_names:
            continue
        column_names = {
            column["name"] for column in inspect(engine).get_columns(table)
        }
        with engine.begin() as connection:
            for legacy_name, current_name in column_mapping.items():
                if legacy_name not in column_names or current_name in column_names:
                    continue
                connection.execute(
                    text(
                        f'ALTER TABLE "{table}" '
                        f'RENAME COLUMN "{legacy_name}" TO "{current_name}"'
                    )
                )
                column_names.remove(legacy_name)
                column_names.add(current_name)


def _migrate_primary_keys(engine: Engine) -> None:
    table_names = set(inspect(engine).get_table_names())
    for table, business_key in BUSINESS_KEY_COLUMNS.items():
        if table not in table_names:
            continue
        columns = _column_map(engine, table)
        id_column = columns.get(PRIMARY_KEY_COLUMN)
        business_key_exists = business_key in columns
        if id_column is None:
            if business_key_exists:
                _add_identity_primary_key(engine, table)
            else:
                continue
        elif not _is_integer_column(id_column):
            _split_legacy_primary_key(
                engine,
                table,
                business_key,
                business_key_exists,
            )
        elif not business_key_exists:
            _add_business_key(engine, table, business_key)
        _ensure_business_key_values(engine, table, business_key)
        _ensure_business_key_constraints(engine, table, business_key)
        _ensure_identity_primary_key(engine, table)


def _split_legacy_primary_key(
    engine: Engine,
    table: str,
    business_key: str,
    business_key_exists: bool,
) -> None:
    primary_key = inspect(engine).get_pk_constraint(table)
    with engine.begin() as connection:
        if primary_key.get("name"):
            connection.execute(
                text(
                    f'ALTER TABLE "{table}" '
                    f'DROP CONSTRAINT "{primary_key["name"]}"'
                )
            )
        if business_key_exists:
            connection.execute(
                text(
                    f'UPDATE "{table}" SET "{business_key}" = '
                    f'"{PRIMARY_KEY_COLUMN}" '
                    f'WHERE "{business_key}" IS NULL'
                )
            )
            connection.execute(
                text(
                    f'ALTER TABLE "{table}" '
                    f'DROP COLUMN "{PRIMARY_KEY_COLUMN}"'
                )
            )
        else:
            connection.execute(
                text(
                    f'ALTER TABLE "{table}" '
                    f'RENAME COLUMN "{PRIMARY_KEY_COLUMN}" '
                    f'TO "{business_key}"'
                )
            )
    _add_identity_primary_key(engine, table)


def _add_identity_primary_key(engine: Engine, table: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                f'ALTER TABLE "{table}" ADD COLUMN "{PRIMARY_KEY_COLUMN}" '
                "BIGINT GENERATED BY DEFAULT AS IDENTITY"
            )
        )
        connection.execute(
            text(
                f'ALTER TABLE "{table}" '
                f'ADD PRIMARY KEY ("{PRIMARY_KEY_COLUMN}")'
            )
        )


def _add_business_key(engine: Engine, table: str, business_key: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                f'ALTER TABLE "{table}" ADD COLUMN "{business_key}" '
                "VARCHAR(36)"
            )
        )


def _ensure_business_key_values(
    engine: Engine,
    table: str,
    business_key: str,
) -> None:
    columns = _column_map(engine, table)
    business_column = columns.get(business_key)
    if business_column is None:
        return
    with engine.begin() as connection:
        rows = connection.execute(
            text(
                f'SELECT "{PRIMARY_KEY_COLUMN}" FROM "{table}" '
                f'WHERE "{business_key}" IS NULL'
            )
        ).fetchall()
        for (row_id,) in rows:
            connection.execute(
                text(
                    f'UPDATE "{table}" SET "{business_key}" = :business_key '
                    f'WHERE "{PRIMARY_KEY_COLUMN}" = :row_id'
                ),
                {"business_key": str(uuid4()), "row_id": row_id},
            )
        if business_column.get("nullable"):
            connection.execute(
                text(
                    f'ALTER TABLE "{table}" '
                    f'ALTER COLUMN "{business_key}" SET NOT NULL'
                )
            )


def _ensure_business_key_constraints(
    engine: Engine,
    table: str,
    business_key: str,
) -> None:
    if not _has_unique_key(engine, table, business_key):
        constraint_name = f"uq_{table}_{business_key}"
        with engine.begin() as connection:
            connection.execute(
                text(
                    f'ALTER TABLE "{table}" ADD CONSTRAINT "{constraint_name}" '
                    f'UNIQUE ("{business_key}")'
                )
            )


def _ensure_identity_primary_key(engine: Engine, table: str) -> None:
    columns = _column_map(engine, table)
    id_column = columns.get(PRIMARY_KEY_COLUMN)
    if id_column is None or not _is_integer_column(id_column):
        return
    if "BIGINT" not in str(id_column.get("type", "")).upper():
        with engine.begin() as connection:
            connection.execute(
                text(
                    f'ALTER TABLE "{table}" ALTER COLUMN '
                    f'"{PRIMARY_KEY_COLUMN}" TYPE BIGINT'
                )
            )
        id_column = _column_map(engine, table)[PRIMARY_KEY_COLUMN]
    if not id_column.get("identity") and not id_column.get("default"):
        with engine.begin() as connection:
            connection.execute(
                text(
                    f'ALTER TABLE "{table}" ALTER COLUMN '
                    f'"{PRIMARY_KEY_COLUMN}" '
                    "ADD GENERATED BY DEFAULT AS IDENTITY"
                )
            )
    primary_key = inspect(engine).get_pk_constraint(table)
    if primary_key.get("constrained_columns") == [PRIMARY_KEY_COLUMN]:
        return
    with engine.begin() as connection:
        if primary_key.get("name"):
            connection.execute(
                text(
                    f'ALTER TABLE "{table}" '
                    f'DROP CONSTRAINT "{primary_key["name"]}"'
                )
            )
        connection.execute(
            text(
                f'ALTER TABLE "{table}" '
                f'ADD PRIMARY KEY ("{PRIMARY_KEY_COLUMN}")'
            )
        )


def _has_unique_key(engine: Engine, table: str, column: str) -> bool:
    inspector = inspect(engine)
    for constraint in inspector.get_unique_constraints(table):
        if constraint.get("column_names") == [column]:
            return True
    for index in inspector.get_indexes(table):
        if index.get("unique") and index.get("column_names") == [column]:
            return True
    return False


def _column_map(engine: Engine, table: str) -> dict[str, dict]:
    return {
        column["name"]: column
        for column in inspect(engine).get_columns(table)
    }


def _is_integer_column(column: dict) -> bool:
    return "INT" in str(column.get("type", "")).upper()


class PostgresCaseStore:
    """PostgreSQL case repository with validated JSON payload snapshots."""

    def __init__(self, database_url: str, connect_timeout_seconds: int = 5) -> None:
        self.database_url = database_url
        self.engine: Engine = create_engine(
            database_url,
            pool_pre_ping=True,
            connect_args={"connect_timeout": connect_timeout_seconds},
        )
        self._session_factory = sessionmaker(
            bind=self.engine,
            class_=Session,
            expire_on_commit=False,
        )
        # Create new tables before running additive compatibility migrations.
        # Existing installations still receive the owner column and index.
        Base.metadata.create_all(self.engine)
        migrate_database_identifiers(self.engine)

    def save(self, case: CaseRead) -> CaseRead:
        with self._session_factory.begin() as session:
            row = self._row_by_key(session, case.id)
            if row is None:
                session.add(
                    CaseRow(
                        case_key=case.id,
                        owner_id=case.owner_id,
                        status=case.status,
                        created_at=case.created_at,
                        updated_at=case.updated_at,
                        payload_json=case.model_dump_json(),
                    )
                )
            else:
                row.owner_id = case.owner_id
                row.status = case.status
                row.updated_at = case.updated_at
                row.payload_json = case.model_dump_json()
        return case

    def get(self, case_id: str) -> CaseRead | None:
        with self._session_factory() as session:
            row = self._row_by_key(session, case_id)
        return self._decode(row.payload_json, owner_id=row.owner_id) if row else None

    def list(
        self,
        *,
        owner_id: str | None = None,
        status: str | None = None,
        from_at: datetime | None = None,
        to_at: datetime | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[CaseRead]:
        query = select(CaseRow)
        if owner_id is not None:
            query = query.where(CaseRow.owner_id == owner_id)
        if status is not None:
            query = query.where(CaseRow.status == status)
        if from_at is not None:
            query = query.where(CaseRow.updated_at >= from_at)
        if to_at is not None:
            query = query.where(CaseRow.updated_at < to_at)
        with self._session_factory() as session:
            rows = session.scalars(
                query.order_by(CaseRow.updated_at.desc())
                .offset(offset)
                .limit(limit)
            ).all()
        return [
            self._decode(row.payload_json, owner_id=row.owner_id)
            for row in rows
        ]

    def count(
        self,
        *,
        owner_id: str | None = None,
        status: str | None = None,
        from_at: datetime | None = None,
        to_at: datetime | None = None,
    ) -> int:
        query = select(func.count()).select_from(CaseRow)
        if owner_id is not None:
            query = query.where(CaseRow.owner_id == owner_id)
        if status is not None:
            query = query.where(CaseRow.status == status)
        if from_at is not None:
            query = query.where(CaseRow.updated_at >= from_at)
        if to_at is not None:
            query = query.where(CaseRow.updated_at < to_at)
        with self._session_factory() as session:
            return int(session.execute(query).scalar_one())

    def stats(self, *, owner_id: str | None = None) -> CaseStats:
        query = select(CaseRow.status, func.count()).group_by(CaseRow.status)
        if owner_id is not None:
            query = query.where(CaseRow.owner_id == owner_id)
        with self._session_factory() as session:
            rows = session.execute(query).all()
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
    def _row_by_key(session, case_key: str) -> CaseRow | None:
        return (
            session.query(CaseRow)
            .filter(CaseRow.case_key == case_key)
            .one_or_none()
        )

    @staticmethod
    def _decode(payload: str, *, owner_id: str = "") -> CaseRead:
        case = CaseRead.model_validate(json.loads(payload))
        if owner_id and case.owner_id != owner_id:
            case = case.model_copy(update={"owner_id": owner_id})
        return case

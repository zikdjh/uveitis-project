from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import or_

from app.core.secret_box import SecretBox
from app.db.models import DataDictionaryRow
from app.schemas.data_dictionary import (
    DataDictionaryEntryRead,
    DictionaryValueType,
)


REVISION_KEY = "_meta.revision"
UPDATED_AT_KEY = "_meta.updated_at"
UPDATED_BY_KEY = "_meta.updated_by"


@dataclass(frozen=True)
class DictionaryValue:
    value: Any = None
    value_type: DictionaryValueType | None = None
    description: str | None = None
    delete: bool = False
    stored_value: str | None = None


def infer_value_type(value: Any, requested: str | None = None) -> DictionaryValueType:
    if requested is not None:
        return requested  # type: ignore[return-value]
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, (dict, list, tuple)):
        return "json"
    return "string"


def _decode_value(
    value_text: str,
    value_type: str,
    secret_box: SecretBox,
    *,
    reveal_secret: bool,
) -> Any:
    if value_type == "secret":
        return secret_box.decrypt(value_text) if reveal_secret else value_text
    if value_type == "json":
        return json.loads(value_text) if value_text else None
    if value_type == "bool":
        return value_text.lower() in {"1", "true", "yes", "on"}
    if value_type == "int":
        return int(value_text)
    if value_type == "float":
        return float(value_text)
    return value_text


def _encode_value(
    value: Any,
    value_type: DictionaryValueType,
    secret_box: SecretBox,
) -> str:
    if value_type == "secret":
        if not isinstance(value, str):
            raise ValueError("敏感数据必须使用字符串")
        return secret_box.encrypt(value)
    if value_type == "json":
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if value_type == "bool":
        return "true" if bool(value) else "false"
    if value_type in {"int", "float"}:
        return str(value)
    if value is None:
        return ""
    return str(value)


def _public_entry(
    *,
    entry_id: str,
    namespace: str,
    key: str,
    value_type: str,
    value_text: str,
    is_secret: bool,
    description: str,
    revision: int,
    created_at: datetime | None,
    updated_at: datetime | None,
    updated_by: str,
    secret_box: SecretBox,
) -> DataDictionaryEntryRead:
    hidden = is_secret or value_type == "secret"
    return DataDictionaryEntryRead(
        id=entry_id,
        namespace=namespace,
        key=key,
        value_type=value_type,  # type: ignore[arg-type]
        value=None if hidden else _decode_value(
            value_text,
            value_type,
            secret_box,
            reveal_secret=False,
        ),
        configured=bool(value_text),
        is_secret=hidden,
        description=description,
        revision=revision,
        created_at=created_at,
        updated_at=updated_at,
        updated_by=updated_by,
    )


class DataDictionaryStore:
    """PostgreSQL-backed key/value registry for runtime configuration."""

    def __init__(self, session_factory, secret_box: SecretBox) -> None:
        self._session_factory = session_factory
        self.secret_box = secret_box
        engine = self._session_factory.kw["bind"]
        DataDictionaryRow.__table__.create(engine, checkfirst=True)

    def get_value(
        self,
        namespace: str,
        key: str,
        *,
        default: Any = None,
        reveal_secret: bool = True,
    ) -> Any:
        with self._session_factory() as session:
            row = session.query(DataDictionaryRow).filter(
                DataDictionaryRow.namespace == namespace,
                DataDictionaryRow.key == key,
            ).one_or_none()
        if row is None:
            return default
        return _decode_value(
            row.value_text,
            row.value_type,
            self.secret_box,
            reveal_secret=reveal_secret,
        )

    def get_stored_value(
        self,
        namespace: str,
        key: str,
        *,
        default: Any = None,
    ) -> Any:
        with self._session_factory() as session:
            row = session.query(DataDictionaryRow).filter(
                DataDictionaryRow.namespace == namespace,
                DataDictionaryRow.key == key,
            ).one_or_none()
        return row.value_text if row is not None else default

    def get_namespace_values(
        self,
        namespace: str,
        *,
        reveal_secret: bool = False,
    ) -> dict[str, Any]:
        with self._session_factory() as session:
            rows = session.query(DataDictionaryRow).filter(
                DataDictionaryRow.namespace == namespace
            ).all()
        return {
            row.key: _decode_value(
                row.value_text,
                row.value_type,
                self.secret_box,
                reveal_secret=reveal_secret,
            )
            for row in rows
        }

    def list_entries(
        self,
        *,
        namespace: str | None = None,
        search: str = "",
        limit: int = 200,
        offset: int = 0,
    ) -> list[DataDictionaryEntryRead]:
        with self._session_factory() as session:
            query = session.query(DataDictionaryRow)
            if namespace:
                query = query.filter(DataDictionaryRow.namespace == namespace)
            if search.strip():
                term = f"%{search.strip()}%"
                query = query.filter(
                    or_(
                        DataDictionaryRow.namespace.ilike(term),
                        DataDictionaryRow.key.ilike(term),
                        DataDictionaryRow.description.ilike(term),
                    )
                )
            rows = (
                query.order_by(
                    DataDictionaryRow.namespace.asc(),
                    DataDictionaryRow.key.asc(),
                )
                .offset(offset)
                .limit(limit)
                .all()
            )
        return [self._read_row(row) for row in rows]

    def get_entry(
        self,
        namespace: str,
        key: str,
    ) -> DataDictionaryEntryRead | None:
        with self._session_factory() as session:
            row = session.query(DataDictionaryRow).filter(
                DataDictionaryRow.namespace == namespace,
                DataDictionaryRow.key == key,
            ).one_or_none()
        return self._read_row(row) if row else None

    def set_value(
        self,
        namespace: str,
        key: str,
        value: Any,
        *,
        value_type: DictionaryValueType | None = None,
        description: str | None = None,
        actor_id: str,
        expected_revision: int | None = None,
    ) -> DataDictionaryEntryRead:
        resolved_type = infer_value_type(value, value_type)
        with self._session_factory.begin() as session:
            row = (
                session.query(DataDictionaryRow)
                .filter(
                    DataDictionaryRow.namespace == namespace,
                    DataDictionaryRow.key == key,
                )
                .with_for_update()
                .one_or_none()
            )
            if (
                expected_revision is not None
                and row is not None
                and row.revision != expected_revision
            ):
                raise ValueError("数据字典项已被其他管理员更新，请刷新后重试")
            if expected_revision is not None and row is None and expected_revision != 0:
                raise ValueError("数据字典项已不存在，请刷新后重试")
            row = self._upsert_row(
                session,
                row,
                namespace=namespace,
                key=key,
                value=value,
                value_type=resolved_type,
                description=description,
                actor_id=actor_id,
            )
            session.flush()
            return self._read_row(row)

    def delete_value(
        self,
        namespace: str,
        key: str,
        *,
        actor_id: str,
        expected_revision: int | None = None,
    ) -> bool:
        if namespace == "auth":
            raise ValueError("认证凭据只能由数据库迁移维护")
        with self._session_factory.begin() as session:
            row = (
                session.query(DataDictionaryRow)
                .filter(
                    DataDictionaryRow.namespace == namespace,
                    DataDictionaryRow.key == key,
                )
                .with_for_update()
                .one_or_none()
            )
            if row is None:
                return False
            if expected_revision is not None and row.revision != expected_revision:
                raise ValueError("数据字典项已被其他管理员更新，请刷新后重试")
            session.delete(row)
        return True

    def update_namespace(
        self,
        namespace: str,
        values: dict[str, DictionaryValue],
        *,
        actor_id: str,
        expected_revision: int | None = None,
        revision: int | None = None,
        updated_at: datetime | None = None,
        updated_by: str | None = None,
    ) -> int:
        now = updated_at or datetime.now(UTC)
        with self._session_factory.begin() as session:
            rows = (
                session.query(DataDictionaryRow)
                .filter(DataDictionaryRow.namespace == namespace)
                .with_for_update()
                .all()
            )
            by_key = {row.key: row for row in rows}
            current_revision = 0
            revision_row = by_key.get(REVISION_KEY)
            if revision_row is not None:
                current_revision = int(revision_row.value_text or 0)
            if (
                expected_revision is not None
                and expected_revision != current_revision
            ):
                raise ValueError("配置已被其他管理员更新，请刷新后重试")
            next_revision = current_revision + 1 if revision is None else revision
            for key, mutation in values.items():
                row = by_key.get(key)
                if mutation.delete:
                    if row is not None:
                        session.delete(row)
                    continue
                row_type = infer_value_type(
                    mutation.value,
                    mutation.value_type,
                )
                stored_value = mutation.stored_value
                if stored_value is None:
                    stored_value = _encode_value(
                        mutation.value,
                        row_type,
                        self.secret_box,
                    )
                row = self._upsert_row(
                    session,
                    row,
                    namespace=namespace,
                    key=key,
                    value=mutation.value,
                    value_type=row_type,
                    value_text=stored_value,
                    description=mutation.description,
                    actor_id=actor_id,
                )
                session.flush()
                by_key[key] = row
            self._set_meta_row(
                session,
                by_key,
                namespace=namespace,
                key=REVISION_KEY,
                value=next_revision,
                value_type="int",
                description="命名空间配置修订号",
                actor_id=actor_id,
                now=now,
            )
            self._set_meta_row(
                session,
                by_key,
                namespace=namespace,
                key=UPDATED_AT_KEY,
                value=now.isoformat(),
                value_type="string",
                description="命名空间最后更新时间",
                actor_id=actor_id,
                now=now,
            )
            self._set_meta_row(
                session,
                by_key,
                namespace=namespace,
                key=UPDATED_BY_KEY,
                value=updated_by if updated_by is not None else actor_id,
                value_type="string",
                description="命名空间最后更新账号",
                actor_id=actor_id,
                now=now,
            )
        return next_revision

    def _upsert_row(
        self,
        session,
        row: DataDictionaryRow | None,
        *,
        namespace: str,
        key: str,
        value: Any,
        value_type: DictionaryValueType,
        description: str | None,
        actor_id: str,
        value_text: str | None = None,
    ) -> DataDictionaryRow:
        now = datetime.now(UTC)
        stored = value_text
        if stored is None:
            stored = _encode_value(value, value_type, self.secret_box)
        if row is None:
            row = DataDictionaryRow(
                dictionary_key=str(uuid4()),
                namespace=namespace,
                key=key,
                value_type=value_type,
                value_text=stored,
                is_secret=value_type == "secret",
                description=(description or "").strip(),
                revision=1,
                created_at=now,
                updated_at=now,
                updated_by=actor_id,
            )
            session.add(row)
            return row
        row.value_type = value_type
        row.value_text = stored
        row.is_secret = value_type == "secret"
        if description is not None:
            row.description = description.strip()
        row.revision += 1
        row.updated_at = now
        row.updated_by = actor_id
        return row

    def _set_meta_row(
        self,
        session,
        by_key: dict[str, DataDictionaryRow],
        namespace: str,
        key: str,
        value: Any,
        *,
        value_type: DictionaryValueType,
        description: str,
        actor_id: str,
        now: datetime,
    ) -> None:
        row = by_key.get(key)
        if row is None:
            row = DataDictionaryRow(
                dictionary_key=str(uuid4()),
                namespace=namespace,
                key=key,
                value_type=value_type,
                value_text="",
                is_secret=False,
                description=description,
                revision=1,
                created_at=now,
                updated_at=now,
                updated_by=actor_id,
            )
            session.add(row)
            by_key[key] = row
        row.value_type = value_type
        row.value_text = _encode_value(value, value_type, self.secret_box)
        row.description = description
        row.revision += 1
        row.updated_at = now
        row.updated_by = actor_id

    def _read_row(self, row: DataDictionaryRow) -> DataDictionaryEntryRead:
        return _public_entry(
            entry_id=row.dictionary_key,
            namespace=row.namespace,
            key=row.key,
            value_type=row.value_type,
            value_text=row.value_text,
            is_secret=bool(row.is_secret),
            description=row.description,
            revision=row.revision,
            created_at=row.created_at,
            updated_at=row.updated_at,
            updated_by=row.updated_by,
            secret_box=self.secret_box,
        )


class MemoryDataDictionaryStore:
    """In-process data dictionary used by isolated tests and local checks."""

    def __init__(self, secret_box: SecretBox) -> None:
        self.secret_box = secret_box
        self._rows: dict[tuple[str, str], dict[str, Any]] = {}

    def get_value(
        self,
        namespace: str,
        key: str,
        *,
        default: Any = None,
        reveal_secret: bool = True,
    ) -> Any:
        row = self._rows.get((namespace, key))
        if row is None:
            return default
        return _decode_value(
            row["value_text"],
            row["value_type"],
            self.secret_box,
            reveal_secret=reveal_secret,
        )

    def get_stored_value(
        self,
        namespace: str,
        key: str,
        *,
        default: Any = None,
    ) -> Any:
        row = self._rows.get((namespace, key))
        return row["value_text"] if row is not None else default

    def get_namespace_values(
        self,
        namespace: str,
        *,
        reveal_secret: bool = False,
    ) -> dict[str, Any]:
        return {
            key: _decode_value(
                row["value_text"],
                row["value_type"],
                self.secret_box,
                reveal_secret=reveal_secret,
            )
            for (row_namespace, key), row in self._rows.items()
            if row_namespace == namespace
        }

    def list_entries(
        self,
        *,
        namespace: str | None = None,
        search: str = "",
        limit: int = 200,
        offset: int = 0,
    ) -> list[DataDictionaryEntryRead]:
        term = search.strip().lower()
        rows = [
            row
            for row in self._rows.values()
            if (not namespace or row["namespace"] == namespace)
            and (
                not term
                or term in row["namespace"].lower()
                or term in row["key"].lower()
                or term in row["description"].lower()
            )
        ]
        rows.sort(key=lambda item: (item["namespace"], item["key"]))
        return [self._read_row(row) for row in rows[offset : offset + limit]]

    def get_entry(
        self,
        namespace: str,
        key: str,
    ) -> DataDictionaryEntryRead | None:
        row = self._rows.get((namespace, key))
        return self._read_row(row) if row else None

    def set_value(
        self,
        namespace: str,
        key: str,
        value: Any,
        *,
        value_type: DictionaryValueType | None = None,
        description: str | None = None,
        actor_id: str,
        expected_revision: int | None = None,
    ) -> DataDictionaryEntryRead:
        resolved_type = infer_value_type(value, value_type)
        current = self._rows.get((namespace, key))
        if expected_revision is not None:
            current_revision = int(current["revision"]) if current else 0
            if expected_revision != current_revision:
                raise ValueError("数据字典项已被其他管理员更新，请刷新后重试")
        row = self._upsert_row(
            current,
            namespace=namespace,
            key=key,
            value=value,
            value_type=resolved_type,
            description=description,
            actor_id=actor_id,
        )
        self._rows[(namespace, key)] = row
        return self._read_row(row)

    def delete_value(
        self,
        namespace: str,
        key: str,
        *,
        actor_id: str,
        expected_revision: int | None = None,
    ) -> bool:
        if namespace == "auth":
            raise ValueError("认证凭据只能由数据库迁移维护")
        current = self._rows.get((namespace, key))
        if current is None:
            return False
        if (
            expected_revision is not None
            and expected_revision != int(current["revision"])
        ):
            raise ValueError("数据字典项已被其他管理员更新，请刷新后重试")
        del self._rows[(namespace, key)]
        return True

    def update_namespace(
        self,
        namespace: str,
        values: dict[str, DictionaryValue],
        *,
        actor_id: str,
        expected_revision: int | None = None,
        revision: int | None = None,
        updated_at: datetime | None = None,
        updated_by: str | None = None,
    ) -> int:
        now = updated_at or datetime.now(UTC)
        current_revision = int(
            self.get_value(namespace, REVISION_KEY, default=0)
        )
        if expected_revision is not None and expected_revision != current_revision:
            raise ValueError("配置已被其他管理员更新，请刷新后重试")
        next_revision = current_revision + 1 if revision is None else revision
        for key, mutation in values.items():
            current = self._rows.get((namespace, key))
            if mutation.delete:
                self._rows.pop((namespace, key), None)
                continue
            row_type = infer_value_type(mutation.value, mutation.value_type)
            stored = mutation.stored_value
            if stored is None:
                stored = _encode_value(
                    mutation.value,
                    row_type,
                    self.secret_box,
                )
            self._rows[(namespace, key)] = self._upsert_row(
                current,
                namespace=namespace,
                key=key,
                value=mutation.value,
                value_type=row_type,
                value_text=stored,
                description=mutation.description,
                actor_id=actor_id,
                now=now,
            )
        for key, value, value_type, description in (
            (REVISION_KEY, next_revision, "int", "命名空间配置修订号"),
            (UPDATED_AT_KEY, now.isoformat(), "string", "命名空间最后更新时间"),
            (
                UPDATED_BY_KEY,
                updated_by if updated_by is not None else actor_id,
                "string",
                "命名空间最后更新账号",
            ),
        ):
            current = self._rows.get((namespace, key))
            self._rows[(namespace, key)] = self._upsert_row(
                current,
                namespace=namespace,
                key=key,
                value=value,
                value_type=value_type,
                description=description,
                actor_id=actor_id,
                now=now,
            )
        return next_revision

    def _upsert_row(
        self,
        row: dict[str, Any] | None,
        *,
        namespace: str,
        key: str,
        value: Any,
        value_type: DictionaryValueType,
        description: str | None,
        actor_id: str,
        now: datetime | None = None,
        value_text: str | None = None,
    ) -> dict[str, Any]:
        timestamp = now or datetime.now(UTC)
        stored = value_text
        if stored is None:
            stored = _encode_value(value, value_type, self.secret_box)
        if row is None:
            return {
                "id": str(uuid4()),
                "namespace": namespace,
                "key": key,
                "value_type": value_type,
                "value_text": stored,
                "is_secret": value_type == "secret",
                "description": (description or "").strip(),
                "revision": 1,
                "created_at": timestamp,
                "updated_at": timestamp,
                "updated_by": actor_id,
            }
        row.update(
            {
                "value_type": value_type,
                "value_text": stored,
                "is_secret": value_type == "secret",
                "description": (
                    description.strip()
                    if description is not None
                    else row["description"]
                ),
                "revision": int(row["revision"]) + 1,
                "updated_at": timestamp,
                "updated_by": actor_id,
            }
        )
        return row

    def _read_row(self, row: dict[str, Any]) -> DataDictionaryEntryRead:
        return _public_entry(
            entry_id=row["id"],
            namespace=row["namespace"],
            key=row["key"],
            value_type=row["value_type"],
            value_text=row["value_text"],
            is_secret=bool(row["is_secret"]),
            description=row["description"],
            revision=int(row["revision"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            updated_by=row["updated_by"],
            secret_box=self.secret_box,
        )

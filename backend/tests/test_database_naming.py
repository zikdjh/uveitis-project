from contextlib import contextmanager

from app.db.models import AuthAuditRow, CaseRow, DataDictionaryRow, UserRow
from app.db.naming import column_name, table_name
from app.db import postgres as postgres_db


def test_database_tables_and_columns_use_project_prefixes() -> None:
    assert UserRow.__tablename__ == table_name("user")
    assert AuthAuditRow.__tablename__ == table_name("auth_audit_event")
    assert CaseRow.__tablename__ == table_name("case")
    assert DataDictionaryRow.__tablename__ == table_name("data_dictionary")

    assert {column.name for column in UserRow.__table__.columns} == {
        column_name("id"),
        column_name("username"),
        column_name("display_name"),
        column_name("role"),
        column_name("password_hash"),
        column_name("is_active"),
        column_name("created_at"),
    }
    assert {column.name for column in CaseRow.__table__.columns} == {
        column_name("id"),
        column_name("status"),
        column_name("created_at"),
        column_name("updated_at"),
        column_name("payload_json"),
    }


def test_legacy_identifiers_are_renamed_before_orm_startup(monkeypatch) -> None:
    tables = {"users", "cases"}
    columns = {
        "users": [{"name": "id"}],
        "cases": [{"name": "id"}],
        "t_user": [{"name": "id"}],
        "t_case": [{"name": "id"}],
    }
    statements: list[str] = []

    class FakeConnection:
        def execute(self, statement) -> None:
            statements.append(str(statement))

    class FakeEngine:
        @contextmanager
        def begin(self):
            yield FakeConnection()

    class FakeInspector:
        def get_table_names(self) -> list[str]:
            return list(tables)

        def get_columns(self, table: str) -> list[dict[str, str]]:
            return columns.get(table, [])

    monkeypatch.setattr(postgres_db, "inspect", lambda _engine: FakeInspector())

    postgres_db.migrate_database_identifiers(FakeEngine())

    assert statements == [
        'ALTER TABLE "users" RENAME TO "t_user"',
        'ALTER TABLE "cases" RENAME TO "t_case"',
        'ALTER TABLE "t_user" RENAME COLUMN "id" TO "f_id"',
        'ALTER TABLE "t_case" RENAME COLUMN "id" TO "f_id"',
    ]

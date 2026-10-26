from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import inspect, text

from app.db.models import UserRow
from app.schemas.auth import UserRead, UserRole, permissions_for_role


def _user_read(
    *,
    user_id: str,
    username: str,
    display_name: str,
    role: str,
    is_active: bool = True,
) -> UserRead:
    normalized_role: UserRole = "admin" if role == "admin" else "doctor"
    return UserRead(
        id=user_id,
        username=username,
        display_name=display_name,
        role=normalized_role,
        is_active=is_active,
        permissions=permissions_for_role(normalized_role),
    )


class UserStore:
    """SQLAlchemy-backed users used by PostgreSQL deployments."""

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        engine = self._session_factory.kw["bind"]
        inspector = inspect(engine)
        if "users" not in inspector.get_table_names():
            return
        columns = {column["name"] for column in inspector.get_columns("users")}
        if "is_active" not in columns:
            default = "1" if engine.dialect.name == "sqlite" else "TRUE"
            with engine.begin() as connection:
                connection.execute(
                    text(
                        f"ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT {default}"
                    )
                )

    def get_by_username(self, username: str) -> tuple[UserRead, str] | None:
        with self._session_factory() as session:
            row = session.query(UserRow).filter(
                UserRow.username == username.strip().lower()
            ).one_or_none()
        if row is None:
            return None
        return self._from_row(row), row.password_hash

    def get(self, user_id: str) -> UserRead | None:
        with self._session_factory() as session:
            row = session.get(UserRow, user_id)
        return self._from_row(row) if row else None

    def list(self) -> list[UserRead]:
        with self._session_factory() as session:
            rows = session.query(UserRow).order_by(UserRow.created_at.asc()).all()
        return [self._from_row(row) for row in rows]

    def create(
        self,
        username: str,
        password_hash: str,
        display_name: str,
        role: UserRole,
        is_active: bool = True,
    ) -> UserRead:
        username = username.strip().lower()
        with self._session_factory.begin() as session:
            exists = session.query(UserRow).filter(UserRow.username == username).one_or_none()
            if exists is not None:
                raise ValueError("账号已存在")
            row = UserRow(
                id=str(uuid4()),
                username=username,
                display_name=display_name.strip(),
                role=role,
                password_hash=password_hash,
                is_active=is_active,
                created_at=datetime.now(UTC),
            )
            session.add(row)
        return self._from_row(row)

    def ensure_user(
        self,
        username: str,
        password_hash: str,
        display_name: str,
        role: UserRole,
    ) -> UserRead:
        username = username.strip().lower()
        with self._session_factory.begin() as session:
            row = session.query(UserRow).filter(
                UserRow.username == username
            ).one_or_none()
            if row is None:
                row = UserRow(
                    id=str(uuid4()),
                    username=username,
                    display_name=display_name,
                    role=role,
                    password_hash=password_hash,
                    is_active=True,
                    created_at=datetime.now(UTC),
                )
                session.add(row)
        return self._from_row(row)

    def update(
        self,
        user_id: str,
        *,
        display_name: str | None = None,
        role: UserRole | None = None,
        is_active: bool | None = None,
    ) -> UserRead | None:
        with self._session_factory.begin() as session:
            row = session.get(UserRow, user_id)
            if row is None:
                return None
            if display_name is not None:
                row.display_name = display_name.strip()
            if role is not None:
                row.role = role
            if is_active is not None:
                row.is_active = is_active
        return self._from_row(row)

    def set_password(self, user_id: str, password_hash: str) -> UserRead | None:
        with self._session_factory.begin() as session:
            row = session.get(UserRow, user_id)
            if row is None:
                return None
            row.password_hash = password_hash
        return self._from_row(row)

    def count_active_admins(self, excluding_user_id: str | None = None) -> int:
        with self._session_factory() as session:
            query = session.query(UserRow).filter(
                UserRow.role == "admin",
                UserRow.is_active.is_(True),
            )
            if excluding_user_id:
                query = query.filter(UserRow.id != excluding_user_id)
            return query.count()

    @staticmethod
    def _from_row(row: UserRow) -> UserRead:
        return _user_read(
            user_id=row.id,
            username=row.username,
            display_name=row.display_name,
            role=row.role,
            is_active=bool(row.is_active),
        )


class SQLiteUserStore:
    """SQLite user repository for the default no-PostgreSQL development mode."""

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
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                )
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(users)").fetchall()
            }
            if "is_active" not in columns:
                connection.execute(
                    "ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1"
                )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)"
            )

    def get_by_username(self, username: str) -> tuple[UserRead, str] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE username = ?",
                (username.strip().lower(),),
            ).fetchone()
        if row is None:
            return None
        return self._from_row(row), str(row["password_hash"])

    def get(self, user_id: str) -> UserRead | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        return self._from_row(row) if row else None

    def list(self) -> list[UserRead]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM users ORDER BY created_at ASC"
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def create(
        self,
        username: str,
        password_hash: str,
        display_name: str,
        role: UserRole,
        is_active: bool = True,
    ) -> UserRead:
        user_id = str(uuid4())
        username = username.strip().lower()
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO users
                    (id, username, display_name, role, password_hash, is_active, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        username,
                        display_name.strip(),
                        role,
                        password_hash,
                        int(is_active),
                        datetime.now(UTC).isoformat(),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("账号已存在") from exc
        user = self.get(user_id)
        if user is None:
            raise RuntimeError("账号创建失败")
        return user

    def ensure_user(
        self,
        username: str,
        password_hash: str,
        display_name: str,
        role: UserRole,
    ) -> UserRead:
        current = self.get_by_username(username)
        if current is not None:
            return current[0]
        return self.create(username, password_hash, display_name, role)

    def update(
        self,
        user_id: str,
        *,
        display_name: str | None = None,
        role: UserRole | None = None,
        is_active: bool | None = None,
    ) -> UserRead | None:
        updates: list[str] = []
        values: list[object] = []
        if display_name is not None:
            updates.append("display_name = ?")
            values.append(display_name.strip())
        if role is not None:
            updates.append("role = ?")
            values.append(role)
        if is_active is not None:
            updates.append("is_active = ?")
            values.append(int(is_active))
        if updates:
            values.append(user_id)
            with self._connect() as connection:
                connection.execute(
                    f"UPDATE users SET {', '.join(updates)} WHERE id = ?",
                    values,
                )
        return self.get(user_id)

    def set_password(self, user_id: str, password_hash: str) -> UserRead | None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (password_hash, user_id),
            )
        return self.get(user_id)

    def count_active_admins(self, excluding_user_id: str | None = None) -> int:
        query = "SELECT COUNT(*) AS count FROM users WHERE role = 'admin' AND is_active = 1"
        params: tuple[str, ...] = ()
        if excluding_user_id:
            query += " AND id != ?"
            params = (excluding_user_id,)
        with self._connect() as connection:
            row = connection.execute(query, params).fetchone()
        return int(row["count"]) if row else 0

    @staticmethod
    def _from_row(row: sqlite3.Row) -> UserRead:
        return _user_read(
            user_id=str(row["id"]),
            username=str(row["username"]),
            display_name=str(row["display_name"]),
            role=str(row["role"]),
            is_active=bool(row["is_active"]),
        )


class MemoryUserStore:
    """In-process user records used by isolated API tests."""

    def __init__(self) -> None:
        self._users: dict[str, tuple[UserRead, str]] = {}

    def get_by_username(self, username: str) -> tuple[UserRead, str] | None:
        return self._users.get(username.strip().lower())

    def get(self, user_id: str) -> UserRead | None:
        return next(
            (user for user, _ in self._users.values() if user.id == user_id),
            None,
        )

    def list(self) -> list[UserRead]:
        return [user for user, _ in self._users.values()]

    def create(
        self,
        username: str,
        password_hash: str,
        display_name: str,
        role: UserRole,
        is_active: bool = True,
    ) -> UserRead:
        username = username.strip().lower()
        if username in self._users:
            raise ValueError("账号已存在")
        user = _user_read(
            user_id=str(uuid4()),
            username=username,
            display_name=display_name.strip(),
            role=role,
            is_active=is_active,
        )
        self._users[username] = (user, password_hash)
        return user

    def ensure_user(
        self,
        username: str,
        password_hash: str,
        display_name: str,
        role: UserRole,
    ) -> UserRead:
        username = username.strip().lower()
        current = self._users.get(username)
        if current is not None:
            return current[0]
        return self.create(username, password_hash, display_name, role)

    def update(
        self,
        user_id: str,
        *,
        display_name: str | None = None,
        role: UserRole | None = None,
        is_active: bool | None = None,
    ) -> UserRead | None:
        for username, (user, password_hash) in list(self._users.items()):
            if user.id != user_id:
                continue
            updated = user.model_copy(
                update={
                    "display_name": display_name.strip() if display_name else user.display_name,
                    "role": role or user.role,
                    "is_active": user.is_active if is_active is None else is_active,
                    "permissions": permissions_for_role(role or user.role),
                }
            )
            self._users[username] = (updated, password_hash)
            return updated
        return None

    def set_password(self, user_id: str, password_hash: str) -> UserRead | None:
        for username, (user, _) in list(self._users.items()):
            if user.id == user_id:
                self._users[username] = (user, password_hash)
                return user
        return None

    def count_active_admins(self, excluding_user_id: str | None = None) -> int:
        return sum(
            1
            for user, _ in self._users.values()
            if user.role == "admin"
            and user.is_active
            and user.id != excluding_user_id
        )

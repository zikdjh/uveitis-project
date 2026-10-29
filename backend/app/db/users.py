from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import inspect, text

from app.core.auth_policy import ROOT_ADMIN_USERNAME, ROOT_PASSWORD_SENTINEL
from app.db.models import UserRow
from app.db.naming import column_name, table_name
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
        is_root=username == ROOT_ADMIN_USERNAME,
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
        table = table_name("user")
        if table not in inspector.get_table_names():
            return
        columns = {column["name"] for column in inspector.get_columns(table)}
        is_active_column = column_name("is_active")
        if is_active_column not in columns:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        f'ALTER TABLE "{table}" ADD COLUMN "{is_active_column}" '
                        "BOOLEAN NOT NULL DEFAULT TRUE"
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
            row = self._row_by_key(session, user_id)
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
                user_key=str(uuid4()),
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
                    user_key=str(uuid4()),
                    username=username,
                    display_name=display_name,
                    role=role,
                    password_hash=password_hash,
                    is_active=True,
                    created_at=datetime.now(UTC),
                )
                session.add(row)
        return self._from_row(row)

    def ensure_single_admin(
        self,
        username: str,
        password_hash: str | None,
        display_name: str,
    ) -> UserRead:
        username = username.strip().lower()
        if username != ROOT_ADMIN_USERNAME:
            raise ValueError(f"系统管理员账号固定为 {ROOT_ADMIN_USERNAME}")
        with self._session_factory.begin() as session:
            root = session.query(UserRow).filter(
                UserRow.username == username
            ).one_or_none()
            if root is None:
                if not password_hash:
                    raise ValueError("root 管理员首次创建必须提供初始密码")
                root = UserRow(
                    user_key=str(uuid4()),
                    username=username,
                    display_name=display_name,
                    role="admin",
                    password_hash=password_hash,
                    is_active=True,
                    created_at=datetime.now(UTC),
                )
                session.add(root)
                session.flush()
            else:
                root.display_name = display_name
                root.role = "admin"
                root.is_active = True
            other_admins = session.query(UserRow).filter(
                UserRow.role == "admin",
                UserRow.user_key != root.user_key,
            ).all()
            for row in other_admins:
                row.role = "doctor"
        return self._from_row(root)

    def update(
        self,
        user_id: str,
        *,
        display_name: str | None = None,
        role: UserRole | None = None,
        is_active: bool | None = None,
    ) -> UserRead | None:
        with self._session_factory.begin() as session:
            row = self._row_by_key(session, user_id)
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
            row = self._row_by_key(session, user_id)
            if row is None:
                return None
            row.password_hash = password_hash
        return self._from_row(row)

    def clear_password_hash(self, username: str) -> UserRead | None:
        with self._session_factory.begin() as session:
            row = session.query(UserRow).filter(
                UserRow.username == username.strip().lower()
            ).one_or_none()
            if row is None:
                return None
            row.password_hash = ROOT_PASSWORD_SENTINEL
        return self._from_row(row)

    def count_active_admins(self, excluding_user_id: str | None = None) -> int:
        with self._session_factory() as session:
            query = session.query(UserRow).filter(
                UserRow.role == "admin",
                UserRow.is_active.is_(True),
            )
            if excluding_user_id:
                query = query.filter(UserRow.user_key != excluding_user_id)
            return query.count()

    @staticmethod
    def _row_by_key(session, user_key: str) -> UserRow | None:
        return (
            session.query(UserRow)
            .filter(UserRow.user_key == user_key)
            .one_or_none()
        )

    @staticmethod
    def _from_row(row: UserRow) -> UserRead:
        return _user_read(
            user_id=row.user_key,
            username=row.username,
            display_name=row.display_name,
            role=row.role,
            is_active=bool(row.is_active),
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

    def ensure_single_admin(
        self,
        username: str,
        password_hash: str | None,
        display_name: str,
    ) -> UserRead:
        username = username.strip().lower()
        if username != ROOT_ADMIN_USERNAME:
            raise ValueError(f"系统管理员账号固定为 {ROOT_ADMIN_USERNAME}")
        for existing_username, (user, existing_password_hash) in list(self._users.items()):
            if user.username == username:
                continue
            if user.role == "admin":
                self._users[existing_username] = (
                    user.model_copy(
                        update={
                            "role": "doctor",
                            "permissions": permissions_for_role("doctor"),
                        }
                    ),
                    existing_password_hash,
                )
        current = self._users.get(username)
        if current is not None:
            self._users[username] = (
                current[0].model_copy(
                    update={
                        "display_name": display_name,
                        "role": "admin",
                        "is_active": True,
                        "is_root": True,
                        "permissions": permissions_for_role("admin"),
                    }
                ),
                current[1],
            )
            return self._users[username][0]
        if not password_hash:
            raise ValueError("root 管理员首次创建必须提供初始密码")
        return self.create(username, password_hash, display_name, "admin")

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

    def clear_password_hash(self, username: str) -> UserRead | None:
        username = username.strip().lower()
        current = self._users.get(username)
        if current is None:
            return None
        self._users[username] = (current[0], ROOT_PASSWORD_SENTINEL)
        return current[0]

    def count_active_admins(self, excluding_user_id: str | None = None) -> int:
        return sum(
            1
            for user, _ in self._users.values()
            if user.role == "admin"
            and user.is_active
            and user.id != excluding_user_id
        )

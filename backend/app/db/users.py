from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.db.models import UserRow
from app.schemas.auth import UserRead, UserRole


class UserStore:
    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def get_by_username(self, username: str) -> tuple[UserRead, str] | None:
        with self._session_factory() as session:
            row = session.query(UserRow).filter(
                UserRow.username == username.strip().lower()
            ).one_or_none()
        if row is None:
            return None
        return (
            UserRead(
                id=row.id,
                username=row.username,
                display_name=row.display_name,
                role=self._role(row.role),
            ),
            row.password_hash,
        )

    def get(self, user_id: str) -> UserRead | None:
        with self._session_factory() as session:
            row = session.get(UserRow, user_id)
        if row is None:
            return None
        return UserRead(
            id=row.id,
            username=row.username,
            display_name=row.display_name,
            role=self._role(row.role),
        )

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
                    created_at=datetime.now(UTC),
                )
                session.add(row)
        return UserRead(
            id=row.id,
            username=row.username,
            display_name=row.display_name,
            role=role,
        )

    @staticmethod
    def _role(value: str) -> UserRole:
        return "admin" if value == "admin" else "doctor"


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
        user = UserRead(
            id=str(uuid4()),
            username=username,
            display_name=display_name,
            role=role,
        )
        self._users[username] = (user, password_hash)
        return user

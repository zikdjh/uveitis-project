from __future__ import annotations

from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe

from pwdlib import PasswordHash

from app.schemas.auth import LoginResponse, UserRead
from app.services.redis_store import RedisStore


class AuthService:
    def __init__(
        self,
        users,
        redis_store: RedisStore,
        ttl_seconds: int,
    ) -> None:
        self.users = users
        self.redis_store = redis_store
        self.ttl_seconds = ttl_seconds
        self.password_hash = PasswordHash.recommended()

    def hash_password(self, password: str) -> str:
        return self.password_hash.hash(password)

    def authenticate(self, username: str, password: str) -> UserRead | None:
        record = self.users.get_by_username(username)
        if record is None:
            return None
        user, password_hash = record
        if not self.password_hash.verify(password, password_hash):
            return None
        return user

    def create_session(self, user: UserRead) -> tuple[str, LoginResponse]:
        token = token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(seconds=self.ttl_seconds)
        self.redis_store.put_session(token, user.id, self.ttl_seconds)
        return token, LoginResponse(user=user, expires_at=expires_at)

    def current_user(self, token: str) -> UserRead | None:
        user_id = self.redis_store.get_session_user_id(token)
        return self.users.get(user_id) if user_id else None

    def logout(self, token: str) -> None:
        self.redis_store.delete_session(token)

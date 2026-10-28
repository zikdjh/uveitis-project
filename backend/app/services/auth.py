from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe

from pwdlib import PasswordHash

from app.core.auth_policy import ROOT_ADMIN_USERNAME
from app.schemas.auth import LoginResponse, SessionRead, UserRead
from app.services.redis_store import RedisStore, session_fingerprint


@dataclass(frozen=True)
class SessionTokens:
    access_token: str
    refresh_token: str
    session_id: str


class AuthService:
    def __init__(
        self,
        users,
        redis_store: RedisStore,
        access_ttl_seconds: int,
        refresh_ttl_seconds: int,
        *,
        refresh_grace_seconds: int = 30,
        login_max_attempts: int = 5,
        login_window_seconds: int = 15 * 60,
        credential_store=None,
    ) -> None:
        self.users = users
        self.redis_store = redis_store
        self.access_ttl_seconds = access_ttl_seconds
        self.refresh_ttl_seconds = refresh_ttl_seconds
        self.refresh_grace_seconds = refresh_grace_seconds
        self.login_max_attempts = login_max_attempts
        self.login_window_seconds = login_window_seconds
        self.credential_store = credential_store
        self.password_hash = PasswordHash.recommended()

    def hash_password(self, password: str) -> str:
        return self.password_hash.hash(password)

    def authenticate(self, username: str, password: str) -> UserRead | None:
        record = self.users.get_by_username(username)
        if record is None:
            return None
        user, _ = record
        if not user.is_active:
            return None
        password_hash = self._password_hash_for(user)
        if not password_hash:
            return None
        if not self.password_hash.verify(password, password_hash):
            return None
        return user

    def verify_password(self, user_id: str, password: str) -> bool:
        user = self.users.get(user_id)
        if user is None or not user.is_active:
            return False
        record = self.users.get_by_username(user.username)
        if record is None:
            return False
        password_hash = self._password_hash_for(user)
        return bool(password_hash) and self.password_hash.verify(
            password,
            password_hash,
        )

    def login_allowed(self, identity: str) -> bool:
        return self.redis_store.login_failure_count(identity) < self.login_max_attempts

    def record_login_failure(self, identity: str) -> int:
        return self.redis_store.record_login_failure(
            identity,
            self.login_window_seconds,
        )

    def clear_login_failures(self, identity: str) -> None:
        self.redis_store.clear_login_failures(identity)

    def create_session(
        self,
        user: UserRead,
        *,
        ip_address: str = "",
        user_agent: str = "",
    ) -> tuple[SessionTokens, LoginResponse]:
        access_token = token_urlsafe(32)
        refresh_token = token_urlsafe(48)
        session = self.redis_store.create_session(
            access_token,
            refresh_token,
            user.id,
            access_ttl_seconds=self.access_ttl_seconds,
            refresh_ttl_seconds=self.refresh_ttl_seconds,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        tokens = SessionTokens(
            access_token=access_token,
            refresh_token=refresh_token,
            session_id=session["session_id"],
        )
        return tokens, self._login_response(user)

    def refresh_session(
        self,
        refresh_token: str,
        *,
        ip_address: str = "",
        user_agent: str = "",
    ) -> tuple[SessionTokens, LoginResponse] | None:
        new_access_token = token_urlsafe(32)
        new_refresh_token = token_urlsafe(48)
        session = self.redis_store.rotate_session(
            refresh_token,
            new_access_token,
            new_refresh_token,
            access_ttl_seconds=self.access_ttl_seconds,
            refresh_ttl_seconds=self.refresh_ttl_seconds,
            refresh_grace_seconds=self.refresh_grace_seconds,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        if session is None:
            return None
        user = self.users.get(session["user_id"])
        if user is None or not user.is_active:
            self.redis_store.delete_session_id(session["user_id"], session["session_id"])
            return None
        tokens = SessionTokens(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            session_id=session["session_id"],
        )
        return tokens, self._login_response(user)

    def current_user(self, access_token: str) -> UserRead | None:
        session = self._session(access_token, "access")
        if session is None:
            return None
        user = self.users.get(session["user_id"])
        if user is None or not user.is_active:
            self.redis_store.delete_session_id(session["user_id"], session["session_id"])
            return None
        return user

    def session_user(self, token: str, token_kind: str = "refresh") -> UserRead | None:
        session = self._session(token, token_kind)
        if session is None:
            return None
        return self.users.get(session["user_id"])

    def list_sessions(self, user_id: str, current_access_token: str) -> list[SessionRead]:
        current = self._session(current_access_token, "access")
        current_session_id = current.get("session_id") if current else ""
        sessions: list[SessionRead] = []
        for item in self.redis_store.list_sessions(user_id):
            try:
                session_id = item["session_id"]
                created_at = datetime.fromisoformat(item["created_at"])
                last_seen_at = datetime.fromisoformat(item["last_seen_at"])
                expires_at = datetime.fromisoformat(item["refresh_expires_at"])
            except (KeyError, ValueError):
                continue
            sessions.append(
                SessionRead(
                    id=session_id,
                    current=session_id == current_session_id,
                    created_at=created_at,
                    last_seen_at=last_seen_at,
                    expires_at=expires_at,
                    ip_address=item.get("ip_address", ""),
                    user_agent=item.get("user_agent", ""),
                )
            )
        return sessions

    def revoke_session(self, user_id: str, session_id: str) -> bool:
        return self.redis_store.delete_session_id(user_id, session_id)

    def revoke_other_sessions(self, user_id: str, current_access_token: str) -> int:
        return self.redis_store.delete_user_sessions(
            user_id,
            keep_token=current_access_token,
            token_kind="access",
        )

    def revoke_all_sessions(self, user_id: str) -> int:
        return self.redis_store.delete_user_sessions(user_id)

    def logout(
        self,
        *,
        access_token: str | None,
        refresh_token: str | None,
        user_id: str | None = None,
    ) -> None:
        if access_token:
            self.redis_store.delete_session(
                access_token,
                token_kind="access",
                user_id=user_id,
            )
            return
        if refresh_token:
            self.redis_store.delete_session(
                refresh_token,
                token_kind="refresh",
                user_id=user_id,
            )

    def current_session_id(self, access_token: str) -> str | None:
        session = self._session(access_token, "access")
        return session.get("session_id") if session else None

    def token_fingerprint(self, token: str) -> str:
        return session_fingerprint(token)

    def _session(self, token: str, token_kind: str) -> dict[str, str] | None:
        ttl_seconds = (
            self.refresh_ttl_seconds if token_kind == "refresh" else self.access_ttl_seconds
        )
        session = self.redis_store.get_session(token, token_kind, ttl_seconds)
        if not session or not session.get("user_id") or not session.get("session_id"):
            return None
        return session

    def _login_response(self, user: UserRead) -> LoginResponse:
        return LoginResponse(
            user=user,
            expires_at=datetime.now(UTC) + timedelta(seconds=self.access_ttl_seconds),
        )

    def _password_hash_for(self, user: UserRead) -> str:
        if user.username == ROOT_ADMIN_USERNAME and self.credential_store is not None:
            value = self.credential_store.get_value(
                "auth",
                "root.password_hash",
                default="",
            )
            if value:
                return str(value)
        record = self.users.get_by_username(user.username)
        return record[1] if record else ""

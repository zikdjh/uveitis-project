from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

from redis import Redis


TokenKind = str


def session_fingerprint(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def _mapping_key(token_kind: TokenKind, token: str) -> str:
    return f"{token_kind}_session:{session_fingerprint(token)}"


def _mapping_key_by_id(token_kind: TokenKind, token_id: str) -> str:
    return f"{token_kind}_session:{token_id}"


def _data_key(session_id: str) -> str:
    return f"session_data:{session_id}"


def _seconds_until(value: str) -> int:
    try:
        expires_at = datetime.fromisoformat(value)
    except ValueError:
        return 1
    return max(1, int((expires_at - datetime.now(UTC)).total_seconds()))


class RedisStore:
    """Redis adapter for paired-token sessions, throttling and review projections."""

    def __init__(self, url: str) -> None:
        self.client = Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
        )

    def ping(self) -> bool:
        return bool(self.client.ping())

    def create_session(
        self,
        access_token: str,
        refresh_token: str,
        user_id: str,
        *,
        access_ttl_seconds: int,
        refresh_ttl_seconds: int,
        ip_address: str = "",
        user_agent: str = "",
    ) -> dict[str, str]:
        now = datetime.now(UTC)
        session_id = uuid4().hex
        access_id = session_fingerprint(access_token)
        refresh_id = session_fingerprint(refresh_token)
        refresh_expires_at = now + timedelta(seconds=refresh_ttl_seconds)
        session = {
            "session_id": session_id,
            "user_id": user_id,
            "access_id": access_id,
            "refresh_id": refresh_id,
            "created_at": now.isoformat(),
            "last_seen_at": now.isoformat(),
            "refresh_expires_at": refresh_expires_at.isoformat(),
            "ip_address": ip_address[:64],
            "user_agent": user_agent[:500],
            "retired_refresh_ids": "[]",
        }
        with self.client.pipeline(transaction=True) as pipe:
            pipe.set(_mapping_key_by_id("access", access_id), session_id, ex=access_ttl_seconds)
            pipe.set(_mapping_key_by_id("refresh", refresh_id), session_id, ex=refresh_ttl_seconds)
            pipe.hset(_data_key(session_id), mapping=session)
            pipe.expire(_data_key(session_id), refresh_ttl_seconds)
            pipe.sadd(f"user_sessions:{user_id}", session_id)
            pipe.expire(f"user_sessions:{user_id}", refresh_ttl_seconds)
            pipe.execute()
        return session

    def get_session(
        self,
        token: str,
        token_kind: TokenKind,
        ttl_seconds: int,
    ) -> dict[str, str] | None:
        session_id = self.client.get(_mapping_key(token_kind, token))
        if not session_id:
            return None
        data_key = _data_key(str(session_id))
        values = self.client.hgetall(data_key)
        if not values:
            self.client.delete(_mapping_key(token_kind, token))
            return None

        now = datetime.now(UTC)
        if token_kind == "refresh":
            values["refresh_expires_at"] = (
                now + timedelta(seconds=ttl_seconds)
            ).isoformat()
        values["last_seen_at"] = now.isoformat()
        refresh_remaining = _seconds_until(values.get("refresh_expires_at", ""))
        with self.client.pipeline(transaction=True) as pipe:
            pipe.hset(
                data_key,
                mapping={
                    "last_seen_at": values["last_seen_at"],
                    "refresh_expires_at": values["refresh_expires_at"],
                },
            )
            if token_kind == "refresh":
                pipe.expire(_mapping_key(token_kind, token), ttl_seconds)
            pipe.expire(data_key, refresh_remaining)
            pipe.expire(f"user_sessions:{values['user_id']}", refresh_remaining)
            pipe.execute()
        return {str(key): str(value) for key, value in values.items()}

    def rotate_session(
        self,
        refresh_token: str,
        new_access_token: str,
        new_refresh_token: str,
        *,
        access_ttl_seconds: int,
        refresh_ttl_seconds: int,
        refresh_grace_seconds: int,
        ip_address: str = "",
        user_agent: str = "",
    ) -> dict[str, str] | None:
        old_refresh_id = session_fingerprint(refresh_token)
        session_id = self.client.get(_mapping_key_by_id("refresh", old_refresh_id))
        if not session_id:
            return None
        data_key = _data_key(str(session_id))
        values = self.client.hgetall(data_key)
        if not values:
            self.client.delete(_mapping_key_by_id("refresh", old_refresh_id))
            return None

        now = datetime.now(UTC)
        refresh_expires_at = now + timedelta(seconds=refresh_ttl_seconds)
        new_access_id = session_fingerprint(new_access_token)
        new_refresh_id = session_fingerprint(new_refresh_token)
        retired = {
            item
            for item in json.loads(values.get("retired_refresh_ids", "[]"))
            if isinstance(item, str)
        }
        retired.add(old_refresh_id)
        old_access_id = values.get("access_id", "")
        values.update(
            {
                "access_id": new_access_id,
                "refresh_id": new_refresh_id,
                "last_seen_at": now.isoformat(),
                "refresh_expires_at": refresh_expires_at.isoformat(),
                "ip_address": ip_address[:64] or values.get("ip_address", ""),
                "user_agent": user_agent[:500] or values.get("user_agent", ""),
                "retired_refresh_ids": json.dumps(sorted(retired)),
            }
        )

        with self.client.pipeline(transaction=True) as pipe:
            pipe.delete(_mapping_key_by_id("access", old_access_id))
            pipe.set(
                _mapping_key_by_id("access", new_access_id),
                session_id,
                ex=access_ttl_seconds,
            )
            pipe.set(
                _mapping_key_by_id("refresh", new_refresh_id),
                session_id,
                ex=refresh_ttl_seconds,
            )
            pipe.expire(_mapping_key_by_id("refresh", old_refresh_id), refresh_grace_seconds)
            for retired_id in retired:
                pipe.expire(
                    _mapping_key_by_id("refresh", retired_id),
                    refresh_grace_seconds,
                )
            pipe.hset(data_key, mapping=values)
            pipe.expire(data_key, refresh_ttl_seconds)
            pipe.expire(f"user_sessions:{values['user_id']}", refresh_ttl_seconds)
            pipe.execute()
        return {str(key): str(value) for key, value in values.items()}

    def list_sessions(self, user_id: str) -> list[dict[str, str]]:
        session_ids = self.client.smembers(f"user_sessions:{user_id}")
        sessions: list[dict[str, str]] = []
        stale: list[str] = []
        for session_id in session_ids:
            values = self.client.hgetall(_data_key(str(session_id)))
            if not values:
                stale.append(str(session_id))
                continue
            values["session_id"] = str(session_id)
            sessions.append({str(key): str(value) for key, value in values.items()})
        if stale:
            self.client.srem(f"user_sessions:{user_id}", *stale)
        return sorted(
            sessions,
            key=lambda item: item.get("last_seen_at", ""),
            reverse=True,
        )

    def get_session_user_id(self, token: str, token_kind: TokenKind = "access") -> str | None:
        session_id = self.client.get(_mapping_key(token_kind, token))
        if not session_id:
            return None
        value = self.client.hget(_data_key(str(session_id)), "user_id")
        return str(value) if value else None

    def delete_session(
        self,
        token: str,
        *,
        token_kind: TokenKind = "access",
        user_id: str | None = None,
    ) -> None:
        session_id = self.client.get(_mapping_key(token_kind, token))
        if session_id:
            self.delete_session_id(user_id or self.get_session_user_id(token, token_kind) or "", str(session_id))
            return
        if user_id:
            self.client.srem(f"user_sessions:{user_id}", session_fingerprint(token))

    def delete_session_id(self, user_id: str, session_id: str) -> bool:
        data_key = _data_key(session_id)
        values = self.client.hgetall(data_key)
        if not values or (user_id and values.get("user_id") != user_id):
            return False
        token_ids = {
            values.get("access_id", ""),
            values.get("refresh_id", ""),
            *json.loads(values.get("retired_refresh_ids", "[]")),
        }
        resolved_user_id = values.get("user_id", user_id)
        with self.client.pipeline(transaction=True) as pipe:
            for token_id in token_ids:
                if not token_id:
                    continue
                pipe.delete(_mapping_key_by_id("access", token_id))
                pipe.delete(_mapping_key_by_id("refresh", token_id))
            pipe.delete(data_key)
            if resolved_user_id:
                pipe.srem(f"user_sessions:{resolved_user_id}", session_id)
            pipe.execute()
        return True

    def delete_user_sessions(
        self,
        user_id: str,
        *,
        keep_token: str | None = None,
        token_kind: TokenKind = "access",
    ) -> int:
        keep_session_id = (
            self.client.get(_mapping_key(token_kind, keep_token))
            if keep_token
            else None
        )
        deleted = 0
        for session_id in self.client.smembers(f"user_sessions:{user_id}"):
            if str(session_id) == keep_session_id:
                continue
            if self.delete_session_id(user_id, str(session_id)):
                deleted += 1
        return deleted

    def login_failure_count(self, identity: str) -> int:
        value = self.client.get(self._login_key(identity))
        return int(value or 0)

    def record_login_failure(self, identity: str, window_seconds: int) -> int:
        key = self._login_key(identity)
        with self.client.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, window_seconds)
            count, _ = pipe.execute()
        return int(count)

    def clear_login_failures(self, identity: str) -> None:
        self.client.delete(self._login_key(identity))

    @staticmethod
    def _login_key(identity: str) -> str:
        digest = sha256(identity.encode("utf-8")).hexdigest()
        return f"login_failures:{digest}"

    def set_review_queue(self, case_ids: Iterable[str]) -> None:
        key = "cases:awaiting_review"
        with self.client.pipeline(transaction=True) as pipe:
            pipe.delete(key)
            ids = list(case_ids)
            if ids:
                pipe.rpush(key, *ids)
            pipe.execute()

    def review_queue(self, limit: int = 100) -> list[str]:
        return [
            str(value)
            for value in self.client.lrange("cases:awaiting_review", 0, limit - 1)
        ]


class MemorySessionStore:
    """In-process paired-token session store used by isolated tests only."""

    def __init__(self) -> None:
        self.session_data: dict[str, dict[str, str]] = {}
        self.token_sessions: dict[str, dict[str, str]] = {
            "access": {},
            "refresh": {},
        }
        self.token_expiries: dict[str, dict[str, datetime]] = {
            "access": {},
            "refresh": {},
        }
        self.user_sessions: dict[str, set[str]] = {}
        self.login_failures: dict[str, int] = {}
        self.queue: list[str] = []

    def ping(self) -> bool:
        return True

    def create_session(
        self,
        access_token: str,
        refresh_token: str,
        user_id: str,
        *,
        access_ttl_seconds: int,
        refresh_ttl_seconds: int,
        ip_address: str = "",
        user_agent: str = "",
    ) -> dict[str, str]:
        now = datetime.now(UTC)
        session_id = uuid4().hex
        access_id = session_fingerprint(access_token)
        refresh_id = session_fingerprint(refresh_token)
        refresh_expires_at = now + timedelta(seconds=refresh_ttl_seconds)
        session = {
            "session_id": session_id,
            "user_id": user_id,
            "access_id": access_id,
            "refresh_id": refresh_id,
            "created_at": now.isoformat(),
            "last_seen_at": now.isoformat(),
            "refresh_expires_at": refresh_expires_at.isoformat(),
            "ip_address": ip_address[:64],
            "user_agent": user_agent[:500],
            "retired_refresh_ids": "[]",
        }
        self.session_data[session_id] = session
        self.token_sessions["access"][access_id] = session_id
        self.token_sessions["refresh"][refresh_id] = session_id
        self.token_expiries["access"][access_id] = now + timedelta(seconds=access_ttl_seconds)
        self.token_expiries["refresh"][refresh_id] = refresh_expires_at
        self.user_sessions.setdefault(user_id, set()).add(session_id)
        return dict(session)

    def get_session(
        self,
        token: str,
        token_kind: TokenKind,
        ttl_seconds: int,
    ) -> dict[str, str] | None:
        token_id = session_fingerprint(token)
        session_id = self.token_sessions[token_kind].get(token_id)
        if not session_id or self.token_expiries[token_kind].get(token_id, datetime.min.replace(tzinfo=UTC)) <= datetime.now(UTC):
            self._delete_token_mapping(token_kind, token_id)
            return None
        session = self.session_data.get(session_id)
        if session is None:
            self._delete_token_mapping(token_kind, token_id)
            return None
        now = datetime.now(UTC)
        session["last_seen_at"] = now.isoformat()
        if token_kind == "refresh":
            session["refresh_expires_at"] = (now + timedelta(seconds=ttl_seconds)).isoformat()
            self.token_expiries["refresh"][token_id] = now + timedelta(seconds=ttl_seconds)
        return dict(session)

    def rotate_session(
        self,
        refresh_token: str,
        new_access_token: str,
        new_refresh_token: str,
        *,
        access_ttl_seconds: int,
        refresh_ttl_seconds: int,
        refresh_grace_seconds: int,
        ip_address: str = "",
        user_agent: str = "",
    ) -> dict[str, str] | None:
        old_refresh_id = session_fingerprint(refresh_token)
        session_id = self.token_sessions["refresh"].get(old_refresh_id)
        if not session_id:
            return None
        session = self.session_data.get(session_id)
        if session is None:
            self._delete_token_mapping("refresh", old_refresh_id)
            return None

        now = datetime.now(UTC)
        old_access_id = session["access_id"]
        new_access_id = session_fingerprint(new_access_token)
        new_refresh_id = session_fingerprint(new_refresh_token)
        retired = set(json.loads(session.get("retired_refresh_ids", "[]")))
        retired.add(old_refresh_id)
        refresh_expires_at = now + timedelta(seconds=refresh_ttl_seconds)
        session.update(
            {
                "access_id": new_access_id,
                "refresh_id": new_refresh_id,
                "last_seen_at": now.isoformat(),
                "refresh_expires_at": refresh_expires_at.isoformat(),
                "ip_address": ip_address[:64] or session.get("ip_address", ""),
                "user_agent": user_agent[:500] or session.get("user_agent", ""),
                "retired_refresh_ids": json.dumps(sorted(retired)),
            }
        )
        self._delete_token_mapping("access", old_access_id)
        self.token_sessions["access"][new_access_id] = session_id
        self.token_sessions["refresh"][new_refresh_id] = session_id
        self.token_expiries["access"][new_access_id] = now + timedelta(seconds=access_ttl_seconds)
        self.token_expiries["refresh"][new_refresh_id] = refresh_expires_at
        self.token_expiries["refresh"][old_refresh_id] = now + timedelta(seconds=refresh_grace_seconds)
        for retired_id in retired:
            self.token_expiries["refresh"][retired_id] = now + timedelta(seconds=refresh_grace_seconds)
        return dict(session)

    def list_sessions(self, user_id: str) -> list[dict[str, str]]:
        now = datetime.now(UTC)
        sessions: list[dict[str, str]] = []
        stale: list[str] = []
        for session_id in self.user_sessions.get(user_id, set()):
            session = self.session_data.get(session_id)
            if session is None or datetime.fromisoformat(session["refresh_expires_at"]) <= now:
                stale.append(session_id)
                continue
            sessions.append(dict(session))
        for session_id in stale:
            self.delete_session_id(user_id, session_id)
        return sorted(
            sessions,
            key=lambda item: item.get("last_seen_at", ""),
            reverse=True,
        )

    def get_session_user_id(self, token: str, token_kind: TokenKind = "access") -> str | None:
        session_id = self.token_sessions[token_kind].get(session_fingerprint(token))
        session = self.session_data.get(session_id) if session_id else None
        return session.get("user_id") if session else None

    def delete_session(
        self,
        token: str,
        *,
        token_kind: TokenKind = "access",
        user_id: str | None = None,
    ) -> None:
        token_id = session_fingerprint(token)
        session_id = self.token_sessions[token_kind].get(token_id)
        if session_id:
            self.delete_session_id(user_id or self.get_session_user_id(token, token_kind) or "", session_id)
        else:
            self._delete_token_mapping(token_kind, token_id)

    def delete_session_id(self, user_id: str, session_id: str) -> bool:
        session = self.session_data.get(session_id)
        if session is None or (user_id and session.get("user_id") != user_id):
            return False
        token_ids = {
            session.get("access_id", ""),
            session.get("refresh_id", ""),
            *json.loads(session.get("retired_refresh_ids", "[]")),
        }
        for token_id in token_ids:
            if not token_id:
                continue
            self._delete_token_mapping("access", token_id)
            self._delete_token_mapping("refresh", token_id)
        self.session_data.pop(session_id, None)
        self.user_sessions.get(session.get("user_id", user_id), set()).discard(session_id)
        return True

    def delete_user_sessions(
        self,
        user_id: str,
        *,
        keep_token: str | None = None,
        token_kind: TokenKind = "access",
    ) -> int:
        keep_session_id = (
            self.token_sessions[token_kind].get(session_fingerprint(keep_token))
            if keep_token
            else None
        )
        deleted = 0
        for session_id in list(self.user_sessions.get(user_id, set())):
            if session_id == keep_session_id:
                continue
            if self.delete_session_id(user_id, session_id):
                deleted += 1
        return deleted

    def login_failure_count(self, identity: str) -> int:
        return self.login_failures.get(identity, 0)

    def record_login_failure(self, identity: str, window_seconds: int) -> int:
        del window_seconds
        self.login_failures[identity] = self.login_failures.get(identity, 0) + 1
        return self.login_failures[identity]

    def clear_login_failures(self, identity: str) -> None:
        self.login_failures.pop(identity, None)

    def set_review_queue(self, case_ids) -> None:
        self.queue = list(case_ids)

    def review_queue(self, limit: int = 100) -> list[str]:
        return self.queue[:limit]

    def _delete_token_mapping(self, token_kind: TokenKind, token_id: str) -> None:
        self.token_sessions[token_kind].pop(token_id, None)
        self.token_expiries[token_kind].pop(token_id, None)

from __future__ import annotations

from collections.abc import Iterable

from redis import Redis


class RedisStore:
    """Small Redis adapter used for sessions and review-work queue projections."""

    def __init__(self, url: str) -> None:
        self.client = Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=3,
        )

    def ping(self) -> bool:
        return bool(self.client.ping())

    def put_session(self, token: str, user_id: str, ttl_seconds: int) -> None:
        key = f"session:{token}"
        with self.client.pipeline(transaction=True) as pipe:
            pipe.hset(key, mapping={"user_id": user_id})
            pipe.expire(key, ttl_seconds)
            pipe.execute()

    def get_session_user_id(self, token: str) -> str | None:
        value = self.client.hget(f"session:{token}", "user_id")
        return str(value) if value else None

    def delete_session(self, token: str) -> None:
        self.client.delete(f"session:{token}")

    def set_review_queue(self, case_ids: Iterable[str]) -> None:
        key = "cases:awaiting_review"
        with self.client.pipeline(transaction=True) as pipe:
            pipe.delete(key)
            ids = list(case_ids)
            if ids:
                pipe.rpush(key, *ids)
            pipe.execute()

    def review_queue(self, limit: int = 100) -> list[str]:
        return [str(value) for value in self.client.lrange(
            "cases:awaiting_review", 0, limit - 1
        )]


class MemorySessionStore:
    """In-process session store used by isolated tests only."""

    def __init__(self) -> None:
        self.sessions: dict[str, str] = {}
        self.queue: list[str] = []

    def ping(self) -> bool:
        return True

    def put_session(self, token: str, user_id: str, ttl_seconds: int) -> None:
        self.sessions[token] = user_id

    def get_session_user_id(self, token: str) -> str | None:
        return self.sessions.get(token)

    def delete_session(self, token: str) -> None:
        self.sessions.pop(token, None)

    def set_review_queue(self, case_ids) -> None:
        self.queue = list(case_ids)

    def review_queue(self, limit: int = 100) -> list[str]:
        return self.queue[:limit]

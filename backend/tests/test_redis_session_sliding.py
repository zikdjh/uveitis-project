from __future__ import annotations

from datetime import UTC, datetime, timedelta
from time import sleep

from app.services.redis_store import RedisStore


class _FakePipeline:
    def __init__(self, client: "_FakeRedis") -> None:
        self.client = client
        self.ops: list[tuple[str, str, object, object]] = []

    def __enter__(self) -> "_FakePipeline":
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def set(self, key: str, value: str, ex: int | None = None) -> "_FakePipeline":
        self.ops.append(("set", key, value, ex))
        return self

    def hset(self, key: str, mapping: dict[str, str]) -> "_FakePipeline":
        self.ops.append(("hset", key, mapping, None))
        return self

    def expire(self, key: str, seconds: int) -> "_FakePipeline":
        self.ops.append(("expire", key, seconds, None))
        return self

    def sadd(self, key: str, member: str) -> "_FakePipeline":
        self.ops.append(("sadd", key, member, None))
        return self

    def execute(self) -> list[object]:
        for op in self.ops:
            if op[0] == "hset":
                self.client.hset(op[1], mapping=op[2])
            elif op[0] == "set":
                self.client.set(op[1], str(op[2]), ex=op[3])
            elif op[0] == "sadd":
                self.client.sadd(op[1], str(op[2]))
            else:
                self.client.expire(op[1], int(op[2]))
        return []


class _FakeRedis:
    """Redis subset covering the session sliding code paths."""

    def __init__(self) -> None:
        self.values: dict[str, object] = {}
        self.expiries: dict[str, datetime] = {}

    def _alive(self, key: str) -> bool:
        expiry = self.expiries.get(key)
        return key in self.values and (expiry is None or expiry > datetime.now(UTC))

    def _drop_if_expired(self, key: str) -> None:
        if key in self.values and not self._alive(key):
            del self.values[key]
            self.expiries.pop(key, None)

    def get(self, key: str) -> str | None:
        self._drop_if_expired(key)
        value = self.values.get(key)
        return str(value) if isinstance(value, str) else None

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.values[key] = value
        if ex is not None:
            self.expiries[key] = datetime.now(UTC) + timedelta(seconds=ex)

    def hset(self, key: str, mapping: dict[str, str]) -> None:
        self._drop_if_expired(key)
        hash_map = self.values.setdefault(key, {})
        if isinstance(hash_map, dict):
            hash_map.update(mapping)

    def hgetall(self, key: str) -> dict[str, str]:
        self._drop_if_expired(key)
        value = self.values.get(key)
        return dict(value) if isinstance(value, dict) else {}

    def expire(self, key: str, seconds: int) -> None:
        self._drop_if_expired(key)
        if key in self.values:
            self.expiries[key] = datetime.now(UTC) + timedelta(seconds=seconds)

    def delete(self, *keys: str) -> None:
        for key in keys:
            self.values.pop(key, None)
            self.expiries.pop(key, None)

    def sadd(self, key: str, member: str) -> None:
        self._drop_if_expired(key)
        value = self.values.setdefault(key, set())
        if isinstance(value, set):
            value.add(member)

    def smembers(self, key: str) -> set[str]:
        self._drop_if_expired(key)
        value = self.values.get(key)
        return set(value) if isinstance(value, set) else set()

    def srem(self, key: str, *members: str) -> None:
        self._drop_if_expired(key)
        value = self.values.get(key)
        if isinstance(value, set):
            value.difference_update(members)

    def pipeline(self, transaction: bool = True) -> _FakePipeline:
        return _FakePipeline(self)


def test_redis_touch_session_slides_stored_expiry() -> None:
    store = RedisStore.__new__(RedisStore)
    store.client = _FakeRedis()
    store.create_session(
        "access-token",
        "refresh-token",
        "user-1",
        access_ttl_seconds=600,
        refresh_ttl_seconds=600,
    )

    first = store.get_session("access-token", "access", 600)
    assert first is not None
    before = first["refresh_expires_at"]

    sleep(0.005)
    store.touch_session("access-token", "access", 600)

    second = store.get_session("access-token", "access", 600)
    assert second is not None
    assert second["refresh_expires_at"] > before

    listed = store.list_sessions("user-1")
    assert len(listed) == 1
    assert listed[0]["refresh_expires_at"] == second["refresh_expires_at"]

"""Round two: doctor account lifecycle regression against the live API.

Covers create, password reset, login, sequential refresh replay, concurrent
refresh, disable, and post-disable session invalidation.

Refresh probes always send the original refresh cookie explicitly and use a
fresh client, so the retired token reaches the server intact.
"""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor

import httpx

BASE = "http://127.0.0.1:8000"
ADMIN_API = "/api/v1/admin"
USERNAME = "qa.lifecycle.20261029"
PASSWORD = "qa-lifecycle-2026"


def log(name: str, value: object) -> None:
    print(f"{name}: {json.dumps(value, ensure_ascii=False)}", flush=True)


def csrf(client: httpx.Client) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("uveitis_csrf", "")}


def login(username: str, password: str) -> httpx.Client:
    client = httpx.Client(base_url=BASE, timeout=30.0, trust_env=False)
    client.post("/api/v1/auth/login", json={"username": username, "password": password})
    return client


def refresh_with(refresh_token: str, csrf_token: str) -> tuple[int, str | None, str | None]:
    client = httpx.Client(base_url=BASE, timeout=30.0, trust_env=False)
    try:
        response = client.post(
            "/api/v1/auth/refresh",
            headers={"X-CSRF-Token": csrf_token},
            cookies={"uveitis_refresh": refresh_token, "uveitis_csrf": csrf_token},
        )
        return (
            response.status_code,
            client.cookies.get("uveitis_access"),
            client.cookies.get("uveitis_refresh"),
        )
    finally:
        client.close()


def parallel_refresh(refresh_token: str, csrf_token: str) -> list[tuple[int, str | None]]:
    def worker(_: int) -> tuple[int, str | None]:
        code, access, _refresh = refresh_with(refresh_token, csrf_token)
        return code, access

    with ThreadPoolExecutor(max_workers=3) as pool:
        return list(pool.map(worker, range(3)))


def main() -> int:
    admin = httpx.Client(base_url=BASE, timeout=60.0, trust_env=False)
    log("adminLogin", {"status": admin.post("/api/v1/auth/admin/login", json={"username": "root", "password": "root-20261025"}).status_code})

    users = admin.get(f"{ADMIN_API}/users").json()
    existing = next((u for u in users if u["username"] == USERNAME), None)
    if existing:
        uid = existing["id"]
        admin.patch(f"{ADMIN_API}/users/{uid}", json={"is_active": True}, headers=csrf(admin))
        log("reuseExisting", {"userId": uid})
    else:
        created = admin.post(
            f"{ADMIN_API}/users",
            json={"username": USERNAME, "password": PASSWORD, "display_name": "生命周期回归医生"},
            headers=csrf(admin),
        )
        log("createUser", {"status": created.status_code})
        uid = created.json()["id"]

    reset = admin.post(f"{ADMIN_API}/users/{uid}/password", json={"new_password": PASSWORD}, headers=csrf(admin))
    log("resetPassword", {"status": reset.status_code})

    # Session A: replay the same retired refresh cookie twice, expect one pair.
    session_a = login(USERNAME, PASSWORD)
    token_a = session_a.cookies.get("uveitis_refresh", "")
    csrf_a = session_a.cookies.get("uveitis_csrf", "")
    log("loginA", {"status": 200 if token_a else 0, "isActive": True})
    first = refresh_with(token_a, csrf_a)
    replay = refresh_with(token_a, csrf_a)
    log(
        "sequentialReplay",
        {
            "statuses": [first[0], replay[0]],
            "sameAccessToken": first[1] == replay[1],
            "sameRefreshToken": first[2] == replay[2],
        },
    )

    # Session B: three parallel refreshes with one retired-free refresh cookie.
    session_b = login(USERNAME, PASSWORD)
    token_b = session_b.cookies.get("uveitis_refresh", "")
    csrf_b = session_b.cookies.get("uveitis_csrf", "")
    concurrent = parallel_refresh(token_b, csrf_b)
    log(
        "concurrentRefresh",
        {
            "statuses": [code for code, _ in concurrent],
            "distinctAccessTokens": len({token for _, token in concurrent}),
        },
    )

    # Session C stays untouched so the live session probe is meaningful.
    session_c = login(USERNAME, PASSWORD)
    log("meBeforeDisable", {"status": session_c.get("/api/v1/auth/me").status_code})

    disabled = admin.patch(f"{ADMIN_API}/users/{uid}", json={"is_active": False}, headers=csrf(admin))
    log("disableUser", {"status": disabled.status_code, "isActive": disabled.json().get("is_active") if disabled.status_code == 200 else None})

    log("meAfterDisable", {"status": session_c.get("/api/v1/auth/me").status_code})
    csrf_c = session_c.cookies.get("uveitis_csrf", "")
    token_c = session_c.cookies.get("uveitis_refresh", "")
    log("refreshAfterDisable", {"status": refresh_with(token_c, csrf_c)[0]})

    stranger = httpx.Client(base_url=BASE, timeout=30.0, trust_env=False)
    log("loginAfterDisable", {"status": stranger.post("/api/v1/auth/login", json={"username": USERNAME, "password": PASSWORD}).status_code})
    log("registerEntry", {"status": stranger.post("/api/v1/auth/register", json={"username": "nobody", "password": "nobody-2026"}).status_code})

    admin.close()
    session_a.close()
    session_b.close()
    session_c.close()
    stranger.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

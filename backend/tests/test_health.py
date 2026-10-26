from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app
from app.db.users import MemoryUserStore
from app.services.redis_store import MemorySessionStore


def make_client(tmp_path: Path, role: str = "doctor") -> TestClient:
    database_path = tmp_path / f"test-{uuid4().hex}.db"
    users = MemoryUserStore()
    sessions = MemorySessionStore()
    app = create_app(
        database_path=database_path,
        upload_dir=tmp_path / "uploads",
        vector_dir=tmp_path / "vectors",
        use_environment_database=False,
        user_store=users,
        redis_store=sessions,
        bootstrap_users=False,
    )
    password = app.state.auth_service.hash_password("test-password")
    users.ensure_user("doctor", password, "测试医生", "doctor")
    users.ensure_user("admin", password, "测试管理员", "admin")
    client = TestClient(app)
    username = "admin" if role == "admin" else "doctor"
    login = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "test-password"},
    )
    assert login.status_code == 200
    client.headers["X-CSRF-Token"] = client.cookies.get("uveitis_csrf")
    return client


def test_health_returns_ready(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["ready"] is True


def test_case_analysis_and_review_workflow(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    created = client.post(
        "/api/v1/cases",
        json={
            "patient_age": 42,
            "patient_sex": "F",
            "complaint": "左眼视物模糊三天",
            "medical_history": "无特殊",
            "affected_eye": "OS",
            "consent_confirmed": True,
        },
    )
    assert created.status_code == 201
    case_id = created.json()["id"]

    upload = client.post(
        f"/api/v1/cases/{case_id}/images",
        data={"kind": "fundus"},
        files={"files": ("fundus.png", b"\x89PNG\r\n\x1a\nfixture", "image/png")},
    )
    assert upload.status_code == 200
    assert len(upload.json()["images"]) == 1

    analyzed = client.post(f"/api/v1/cases/{case_id}/analyze")
    assert analyzed.status_code == 202
    case = client.get(f"/api/v1/cases/{case_id}").json()
    assert case["status"] == "awaiting_review"
    assert case["analysis"]["status"] == "completed"

    reviewed = client.patch(
        f"/api/v1/cases/{case_id}/review",
        json={
            "decision": "accepted",
            "final_impression": "",
            "note": "流程验证通过",
            "reviewer": "测试医生",
        },
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "reviewed"

    overview = client.get("/api/v1/system/overview")
    assert overview.status_code == 200
    assert overview.json()["stats"]["total"] == 1
    assert len(overview.json()["models"]) == 5
    decision = next(
        model for model in overview.json()["models"]
        if model["role"].startswith("补充决策")
    )
    assert decision["required"] is False
    assert decision["enabled"] is False
    assert decision["status"] == "offline"
    decision_stage = next(
        stage for stage in case["analysis"]["stages"]
        if stage["key"] == "decision"
    )
    assert decision_stage["status"] == "skipped"


def test_case_requires_consent(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    response = client.post(
        "/api/v1/cases",
        json={
            "patient_age": 42,
            "patient_sex": "F",
            "complaint": "视物模糊",
            "consent_confirmed": False,
        },
    )
    assert response.status_code == 422


def test_case_requires_authentication(tmp_path: Path) -> None:
    app = create_app(
        database_path=tmp_path / f"test-{uuid4().hex}.db",
        upload_dir=tmp_path / "uploads",
        vector_dir=tmp_path / "vectors",
        use_environment_database=False,
        user_store=MemoryUserStore(),
        redis_store=MemorySessionStore(),
        bootstrap_users=False,
    )
    response = TestClient(app).get("/api/v1/cases")
    assert response.status_code == 401


def test_admin_only_endpoints(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    response = client.get("/api/v1/system/infrastructure")
    assert response.status_code == 403


def test_knowledge_request_validation(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    invalid = client.post(
        "/api/v1/knowledge/search",
        json={"vector": [1.0], "top_k": 5},
    )
    assert invalid.status_code == 422


def test_mutating_request_requires_csrf(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    client.headers.pop("X-CSRF-Token")
    response = client.post(
        "/api/v1/cases",
        json={
            "patient_age": 42,
            "patient_sex": "F",
            "complaint": "视物模糊",
            "consent_confirmed": True,
        },
    )
    assert response.status_code == 403


def test_admin_can_manage_users_and_read_audit(tmp_path: Path) -> None:
    client = make_client(tmp_path, role="admin")
    created = client.post(
        "/api/v1/admin/users",
        json={
            "username": "doctor.new",
            "display_name": "新医生",
            "role": "doctor",
            "password": "new-doctor-password",
        },
    )
    assert created.status_code == 201
    user = created.json()
    assert user["role"] == "doctor"
    assert "case:read" in user["permissions"]

    disabled = client.patch(
        f"/api/v1/admin/users/{user['id']}",
        json={"is_active": False},
    )
    assert disabled.status_code == 200
    assert disabled.json()["is_active"] is False

    audit = client.get("/api/v1/admin/audit-events")
    assert audit.status_code == 200
    assert audit.json()[0]["event"] == "user_update"


def test_doctor_cannot_manage_users(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    assert client.get("/api/v1/admin/users").status_code == 403


def test_disabled_user_cannot_login(tmp_path: Path) -> None:
    admin = make_client(tmp_path, role="admin")
    created = admin.post(
        "/api/v1/admin/users",
        json={
            "username": "disabled",
            "display_name": "停用账号",
            "role": "doctor",
            "password": "disabled-password",
        },
    ).json()
    admin.patch(
        f"/api/v1/admin/users/{created['id']}",
        json={"is_active": False},
    )

    anonymous = TestClient(admin.app)
    response = anonymous.post(
        "/api/v1/auth/login",
        json={"username": "disabled", "password": "disabled-password"},
    )
    assert response.status_code == 401


def test_password_change_revokes_other_sessions(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    sessions = client.get("/api/v1/auth/sessions")
    assert sessions.status_code == 200
    assert len(sessions.json()) == 1

    changed = client.post(
        "/api/v1/auth/password",
        json={
            "current_password": "test-password",
            "new_password": "changed-test-password",
        },
    )
    assert changed.status_code == 204
    current = client.get("/api/v1/auth/me")
    assert current.status_code == 200


def test_refresh_rotates_both_tokens_and_keeps_one_session(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    old_access = client.cookies.get("uveitis_access")
    old_refresh = client.cookies.get("uveitis_refresh")
    assert old_access and old_refresh

    refreshed = client.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 200
    assert client.cookies.get("uveitis_access") != old_access
    assert client.cookies.get("uveitis_refresh") != old_refresh
    assert client.get("/api/v1/auth/me").status_code == 200
    sessions = client.get("/api/v1/auth/sessions")
    assert sessions.status_code == 200
    assert len(sessions.json()) == 1

    old_access_client = TestClient(client.app)
    old_access_client.cookies.set("uveitis_access", old_access, path="/")
    assert old_access_client.get("/api/v1/auth/me").status_code == 401


def test_refresh_without_access_cookie_restores_session(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    refresh_token = client.cookies.get("uveitis_refresh")
    csrf_token = client.cookies.get("uveitis_csrf")
    assert refresh_token and csrf_token

    renewed = TestClient(client.app)
    renewed.cookies.set("uveitis_refresh", refresh_token, path="/api/v1/auth/refresh")
    renewed.cookies.set("uveitis_csrf", csrf_token, path="/")
    renewed.headers["X-CSRF-Token"] = csrf_token
    response = renewed.post("/api/v1/auth/refresh")
    assert response.status_code == 200
    assert renewed.get("/api/v1/auth/me").status_code == 200


def test_refresh_requires_csrf_and_logout_revokes_refresh(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    refresh_token = client.cookies.get("uveitis_refresh")
    csrf_token = client.cookies.get("uveitis_csrf")
    assert refresh_token and csrf_token

    missing_csrf = TestClient(client.app)
    missing_csrf.cookies.set("uveitis_refresh", refresh_token, path="/api/v1/auth/refresh")
    missing_csrf.cookies.set("uveitis_csrf", csrf_token, path="/")
    assert missing_csrf.post("/api/v1/auth/refresh").status_code == 403

    assert client.post("/api/v1/auth/logout").status_code == 204
    revoked = TestClient(client.app)
    revoked.cookies.set("uveitis_refresh", refresh_token, path="/api/v1/auth/refresh")
    revoked.cookies.set("uveitis_csrf", csrf_token, path="/")
    revoked.headers["X-CSRF-Token"] = csrf_token
    assert revoked.post("/api/v1/auth/refresh").status_code == 401


def test_login_is_rate_limited(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    anonymous = TestClient(client.app)
    for _ in range(5):
        response = anonymous.post(
            "/api/v1/auth/login",
            json={"username": "doctor", "password": "wrong-password"},
        )
        assert response.status_code == 401
    blocked = anonymous.post(
        "/api/v1/auth/login",
        json={"username": "doctor", "password": "test-password"},
    )
    assert blocked.status_code == 429


def test_default_sqlite_auth_store_round_trip(tmp_path: Path) -> None:
    app = create_app(
        database_path=tmp_path / "sqlite-auth.db",
        upload_dir=tmp_path / "uploads",
        vector_dir=tmp_path / "vectors",
        use_environment_database=False,
        redis_store=MemorySessionStore(),
        bootstrap_users=False,
    )
    password = app.state.auth_service.hash_password("sqlite-test-password")
    app.state.user_store.ensure_user("sqlite.doctor", password, "本地医生", "doctor")
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "sqlite.doctor", "password": "sqlite-test-password"},
    )
    assert response.status_code == 200
    assert response.json()["user"]["permissions"]

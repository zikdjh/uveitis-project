from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.auth_policy import ROOT_ADMIN_USERNAME, ROOT_PASSWORD_SENTINEL
from app.core.config import settings
from app.core.secret_box import SecretBox
from app.db.audit import MemoryAuthAuditStore
from app.db.data_dictionary import MemoryDataDictionaryStore
from app.main import create_app
from app.db.users import MemoryUserStore
from app.services.redis_store import MemorySessionStore


def make_client(tmp_path: Path, role: str = "doctor") -> TestClient:
    users = MemoryUserStore()
    sessions = MemorySessionStore()
    app = create_app(
        upload_dir=tmp_path / "uploads",
        vector_dir=tmp_path / "vectors",
        use_environment_database=False,
        user_store=users,
        audit_store=MemoryAuthAuditStore(),
        redis_store=sessions,
        bootstrap_users=False,
    )
    password = app.state.auth_service.hash_password("test-password")
    users.ensure_user("doctor", password, "测试医生", "doctor")
    users.ensure_single_admin(ROOT_ADMIN_USERNAME, password, "测试管理员")
    client = TestClient(app)
    username = ROOT_ADMIN_USERNAME if role == "admin" else "doctor"
    login = client.post(
        "/api/v1/auth/admin/login" if role == "admin" else "/api/v1/auth/login",
        json={"username": username, "password": "test-password"},
    )
    assert login.status_code == 200
    client.headers["X-CSRF-Token"] = client.cookies.get("uveitis_csrf")
    return client


def make_isolated_clients(tmp_path: Path) -> tuple[TestClient, TestClient]:
    users = MemoryUserStore()
    sessions = MemorySessionStore()
    app = create_app(
        upload_dir=tmp_path / "uploads",
        vector_dir=tmp_path / "vectors",
        use_environment_database=False,
        user_store=users,
        audit_store=MemoryAuthAuditStore(),
        redis_store=sessions,
        bootstrap_users=False,
    )
    password = app.state.auth_service.hash_password("test-password")
    users.ensure_user("doctor-a", password, "医生甲", "doctor")
    users.ensure_user("doctor-b", password, "医生乙", "doctor")
    users.ensure_single_admin(ROOT_ADMIN_USERNAME, password, "测试管理员")
    clients: list[TestClient] = []
    for username in ("doctor-a", "doctor-b"):
        client = TestClient(app)
        login = client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": "test-password"},
        )
        assert login.status_code == 200
        client.headers["X-CSRF-Token"] = client.cookies.get("uveitis_csrf")
        clients.append(client)
    return clients[0], clients[1]


def test_health_returns_ready(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["ready"] is True


def test_api_responses_expose_timing_headers(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    response = client.get("/api/v1/health")
    assert response.headers["X-Trace-Id"]
    process_time = float(response.headers["X-Process-Time-Ms"])
    assert process_time >= 0

    forwarded = client.get(
        "/api/v1/health", headers={"X-Trace-Id": "caller-supplied-id"}
    )
    assert forwarded.headers["X-Trace-Id"] == "caller-supplied-id"


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
    assert client.get(f"/api/v1/cases/{case_id}/analysis-job").json() is None

    upload = client.post(
        f"/api/v1/cases/{case_id}/images",
        data={"kind": "fundus"},
        files={"files": ("fundus.png", b"\x89PNG\r\n\x1a\nfixture", "image/png")},
    )
    assert upload.status_code == 200
    assert len(upload.json()["images"]) == 1

    analyzed = client.post(f"/api/v1/cases/{case_id}/analyze")
    assert analyzed.status_code == 202
    job = client.get(f"/api/v1/cases/{case_id}/analysis-job")
    assert job.status_code == 200
    assert job.json()["status"] == "completed"
    assert job.json()["attempt_count"] == 1
    assert job.json()["max_attempts"] >= 1
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
    assert len(overview.json()["models"]) == 6
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
    assert case["analysis"]["summary"]
    qwen_stage = next(
        stage for stage in case["analysis"]["stages"]
        if stage["key"] == "qwen_judgment"
    )
    assert qwen_stage["status"] == "skipped"
    assert case["analysis"]["external_summary_used"] is False


def test_doctor_cannot_access_another_doctors_case(tmp_path: Path) -> None:
    doctor_a, doctor_b = make_isolated_clients(tmp_path)
    created = doctor_a.post(
        "/api/v1/cases",
        json={
            "patient_age": 42,
            "patient_sex": "F",
            "complaint": "医生甲的病人",
            "consent_confirmed": True,
        },
    )
    assert created.status_code == 201
    case_id = created.json()["id"]
    assert created.json()["owner_name"] == "医生甲"

    own_list = doctor_a.get("/api/v1/cases").json()
    assert own_list["total"] == 1
    assert own_list["items"][0]["id"] == case_id

    other_list = doctor_b.get("/api/v1/cases").json()
    assert other_list["total"] == 0
    assert other_list["items"] == []
    own_overview = doctor_a.get("/api/v1/system/overview").json()
    other_overview = doctor_b.get("/api/v1/system/overview").json()
    assert own_overview["stats"]["total"] == 1
    assert other_overview["stats"]["total"] == 0
    assert doctor_b.get(f"/api/v1/cases/{case_id}").status_code == 404
    assert doctor_b.get(f"/api/v1/cases/{case_id}/analysis-job").status_code == 404
    assert doctor_b.post(f"/api/v1/cases/{case_id}/analyze").status_code == 404
    assert doctor_b.patch(
        f"/api/v1/cases/{case_id}/review",
        json={
            "decision": "accepted",
            "final_reason": "越权尝试",
            "reviewer": "医生乙",
        },
    ).status_code == 404


def test_admin_can_audit_cases_across_doctors(tmp_path: Path) -> None:
    doctor_a, _ = make_isolated_clients(tmp_path)
    created = doctor_a.post(
        "/api/v1/cases",
        json={
            "patient_age": 42,
            "patient_sex": "F",
            "complaint": "管理员审计病例",
            "consent_confirmed": True,
        },
    )
    assert created.status_code == 201
    app = doctor_a.app
    admin = TestClient(app)
    login = admin.post(
        "/api/v1/auth/admin/login",
        json={"username": ROOT_ADMIN_USERNAME, "password": "test-password"},
    )
    assert login.status_code == 200
    admin.headers["X-CSRF-Token"] = admin.cookies.get("uveitis_csrf")
    result = admin.get(
        "/api/v1/cases?page=1&page_size=1&status=created"
    ).json()
    assert result["total"] == 1
    assert result["page"] == 1
    assert result["page_size"] == 1
    assert result["items"][0]["owner_name"] == "医生甲"
    assert admin.get(
        "/api/v1/cases?status=reviewed"
    ).json()["total"] == 0
    today = created.json()["updated_at"][:10]
    assert admin.get(
        f"/api/v1/cases?from={today}&to={today}"
    ).json()["total"] == 1
    assert admin.get(
        "/api/v1/cases?from=2999-01-01&to=2999-01-02"
    ).json()["total"] == 0
    assert admin.post(
        "/api/v1/cases",
        json={
            "patient_age": 42,
            "patient_sex": "F",
            "complaint": "管理员不应创建临床病例",
            "consent_confirmed": True,
        },
    ).status_code == 403


def test_case_list_filters_and_paginates_on_server(tmp_path: Path) -> None:
    doctor, _ = make_isolated_clients(tmp_path)
    for index in range(3):
        created = doctor.post(
            "/api/v1/cases",
            json={
                "patient_age": 40 + index,
                "patient_sex": "F",
                "complaint": f"分页病例 {index}",
                "consent_confirmed": True,
            },
        )
        assert created.status_code == 201

    first = doctor.get("/api/v1/cases?page=1&page_size=2").json()
    second = doctor.get("/api/v1/cases?page=2&page_size=2").json()
    assert first["total"] == 3
    assert len(first["items"]) == 2
    assert len(second["items"]) == 1
    assert doctor.get("/api/v1/cases?status=reviewed").json()["total"] == 0
    assert doctor.get("/api/v1/cases?from=not-a-date").status_code == 422


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
        upload_dir=tmp_path / "uploads",
        vector_dir=tmp_path / "vectors",
        use_environment_database=False,
        user_store=MemoryUserStore(),
        audit_store=MemoryAuthAuditStore(),
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
    audit_page = audit.json()
    assert audit_page["items"][0]["event"] == "user_update"
    assert audit_page["total"] >= 1
    assert audit_page["page"] == 1
    assert audit_page["page_size"] == 20
    filtered = client.get(
        "/api/v1/admin/audit-events?event=user_update&outcome=success"
    ).json()
    assert filtered["total"] >= 1
    assert all(item["event"] == "user_update" for item in filtered["items"])
    searched = client.get(
        "/api/v1/admin/audit-events?search=doctor.new&page_size=1"
    ).json()
    assert searched["total"] >= 1
    assert len(searched["items"]) == 1
    today = searched["items"][0]["created_at"][:10]
    dated = client.get(
        f"/api/v1/admin/audit-events?from={today}&to={today}"
    ).json()
    assert dated["total"] >= 1
    assert client.get(
        "/api/v1/admin/audit-events?from=2026-10-28&to=2026-10-27"
    ).status_code == 422
    assert client.get(
        "/api/v1/admin/audit-events?event=unknown"
    ).status_code == 422
    assert client.get(
        "/api/v1/admin/audit-events?outcome=unknown"
    ).status_code == 422


def test_doctor_cannot_manage_users(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    assert client.get("/api/v1/admin/users").status_code == 403


def test_integration_config_is_admin_managed_and_secret_is_write_only(
    tmp_path: Path,
) -> None:
    doctor = make_client(tmp_path)
    assert doctor.get("/api/v1/admin/integrations").status_code == 403
    assert doctor.get("/api/v1/admin/integrations/status").status_code == 200

    admin = make_client(tmp_path, role="admin")
    initial = admin.get("/api/v1/admin/integrations")
    assert initial.status_code == 200
    assert initial.json()["summary_api_key_configured"] is False

    updated = admin.patch(
        "/api/v1/admin/integrations",
        json={
            "summary_enabled": True,
            "summary_protocol": "openai_responses",
            "summary_base_url": "https://summary.example/v1",
            "summary_model": "summary-model",
            "summary_api_key": "secret-never-returned",
            "expected_revision": initial.json()["revision"],
        },
    )
    assert updated.status_code == 200
    assert updated.json()["summary_api_key_configured"] is True
    assert "secret-never-returned" not in updated.text
    assert "summary_api_key" not in updated.json()
    assert updated.json()["revision"] == initial.json()["revision"] + 1

    conflict = admin.patch(
        "/api/v1/admin/integrations",
        json={"summary_model": "stale", "expected_revision": 0},
    )
    assert conflict.status_code == 409

    audit = admin.get("/api/v1/admin/audit-events")
    assert audit.status_code == 200
    assert audit.json()["items"][0]["event"] == "integration_config_update"


def test_admin_and_doctor_use_separate_login_entries(tmp_path: Path) -> None:
    app = create_app(
        upload_dir=tmp_path / "uploads",
        vector_dir=tmp_path / "vectors",
        use_environment_database=False,
        user_store=MemoryUserStore(),
        audit_store=MemoryAuthAuditStore(),
        redis_store=MemorySessionStore(),
        bootstrap_users=False,
    )
    password = app.state.auth_service.hash_password("test-password")
    app.state.user_store.ensure_user("doctor", password, "测试医生", "doctor")
    app.state.user_store.ensure_single_admin(
        ROOT_ADMIN_USERNAME, password, "测试管理员"
    )

    doctor_client = TestClient(app)
    doctor_client.headers["X-CSRF-Token"] = "unused"
    doctor_rejected = doctor_client.post(
        "/api/v1/auth/login",
        json={"username": ROOT_ADMIN_USERNAME, "password": "test-password"},
    )
    assert doctor_rejected.status_code == 403

    admin_client = TestClient(app)
    admin_client.headers["X-CSRF-Token"] = "unused"
    admin_rejected = admin_client.post(
        "/api/v1/auth/admin/login",
        json={"username": "doctor", "password": "test-password"},
    )
    assert admin_rejected.status_code == 403

    accepted = admin_client.post(
        "/api/v1/auth/admin/login",
        json={"username": ROOT_ADMIN_USERNAME, "password": "test-password"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["user"]["role"] == "admin"


def test_runtime_requires_postgres_database(tmp_path: Path) -> None:
    production_settings = settings.model_copy(
        update={"environment": "production", "database_url": ""}
    )
    with pytest.raises(RuntimeError, match="APP_DATABASE_URL"):
        create_app(
            upload_dir=tmp_path / "uploads",
            vector_dir=tmp_path / "vectors",
            use_environment_database=True,
            bootstrap_users=False,
            runtime_settings=production_settings,
        )


def test_disabled_user_cannot_login(tmp_path: Path) -> None:
    admin = make_client(tmp_path, role="admin")
    created = admin.post(
        "/api/v1/admin/users",
        json={
            "username": "disabled",
            "display_name": "停用账号",
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


def test_delete_doctor_is_logical_and_blocks_login(tmp_path: Path) -> None:
    admin = make_client(tmp_path, role="admin")
    created = admin.post(
        "/api/v1/admin/users",
        json={
            "username": "todelete",
            "display_name": "待删除医生",
            "password": "todelete-password",
        },
    ).json()
    doctor_client = TestClient(admin.app)
    doctor_login = doctor_client.post(
        "/api/v1/auth/login",
        json={"username": "todelete", "password": "todelete-password"},
    )
    assert doctor_login.status_code == 200

    deleted = admin.delete(f"/api/v1/admin/users/{created['id']}")
    assert deleted.status_code == 204

    listed = admin.get("/api/v1/admin/users").json()
    assert all(item["id"] != created["id"] for item in listed)
    included = admin.get("/api/v1/admin/users?include_deleted=true").json()
    target = next(item for item in included if item["id"] == created["id"])
    assert target["is_deleted"] is True
    assert target["is_active"] is False

    revoked = doctor_client.get("/api/v1/auth/me")
    assert revoked.status_code == 401
    relogin = TestClient(admin.app).post(
        "/api/v1/auth/login",
        json={"username": "todelete", "password": "todelete-password"},
    )
    assert relogin.status_code == 401

    again = admin.delete(f"/api/v1/admin/users/{created['id']}")
    assert again.status_code == 409

    root_user = next(
        item
        for item in admin.get("/api/v1/admin/users?include_deleted=true").json()
        if item["is_root"]
    )
    root_delete = admin.delete(f"/api/v1/admin/users/{root_user['id']}")
    assert root_delete.status_code == 409

    audit = admin.get("/api/v1/admin/audit-events?event=user_delete").json()
    assert audit["total"] >= 1


def test_admin_can_edit_doctor_display_name(tmp_path: Path) -> None:
    admin = make_client(tmp_path, role="admin")
    created = admin.post(
        "/api/v1/admin/users",
        json={
            "username": "renamed",
            "display_name": "改名前",
            "password": "rename-password",
        },
    ).json()
    updated = admin.patch(
        f"/api/v1/admin/users/{created['id']}",
        json={"display_name": "改名后"},
    )
    assert updated.status_code == 200
    assert updated.json()["display_name"] == "改名后"
    assert updated.json()["is_active"] is True

    root_user = next(
        item
        for item in admin.get("/api/v1/admin/users").json()
        if item["is_root"]
    )
    root_rename = admin.patch(
        f"/api/v1/admin/users/{root_user['id']}",
        json={"display_name": "新管理员名"},
    )
    assert root_rename.status_code == 409

    audit = admin.get("/api/v1/admin/audit-events?event=user_update").json()
    assert any("显示名改为 改名后" in item["detail"] for item in audit["items"])


def test_admin_can_edit_doctor_username(tmp_path: Path) -> None:
    admin = make_client(tmp_path, role="admin")
    created = admin.post(
        "/api/v1/admin/users",
        json={
            "username": "rename.target",
            "display_name": "改名医生",
            "password": "rename-password-123",
        },
    ).json()
    renamed = admin.patch(
        f"/api/v1/admin/users/{created['id']}",
        json={"username": "rename.new"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["username"] == "rename.new"

    reserved = admin.patch(
        f"/api/v1/admin/users/{created['id']}",
        json={"username": "root"},
    )
    assert reserved.status_code == 409

    root_user = next(
        item
        for item in admin.get("/api/v1/admin/users").json()
        if item["is_root"]
    )
    root_rename = admin.patch(
        f"/api/v1/admin/users/{root_user['id']}",
        json={"username": "notroot"},
    )
    assert root_rename.status_code == 409

    other = admin.post(
        "/api/v1/admin/users",
        json={
            "username": "rename.other",
            "display_name": "另一名医生",
            "password": "rename-password-123",
        },
    ).json()
    duplicate = admin.patch(
        f"/api/v1/admin/users/{other['id']}",
        json={"username": "rename.new"},
    )
    assert duplicate.status_code == 409

    doctor = TestClient(admin.app)
    login = doctor.post(
        "/api/v1/auth/login",
        json={"username": "rename.new", "password": "rename-password-123"},
    )
    assert login.status_code == 200

    audit = admin.get("/api/v1/admin/audit-events?event=user_update").json()
    assert any("登录账号改为 rename.new" in item["detail"] for item in audit["items"])


def test_analysis_queue_scopes_by_role(tmp_path: Path) -> None:
    users = MemoryUserStore()
    app = create_app(
        upload_dir=tmp_path / "uploads",
        vector_dir=tmp_path / "vectors",
        use_environment_database=False,
        user_store=users,
        audit_store=MemoryAuthAuditStore(),
        redis_store=MemorySessionStore(),
        bootstrap_users=False,
    )
    password = app.state.auth_service.hash_password("test-password")
    users.ensure_user("doctor-a", password, "医生甲", "doctor")
    users.ensure_user("doctor-b", password, "医生乙", "doctor")
    users.ensure_single_admin(ROOT_ADMIN_USERNAME, password, "测试管理员")

    def login(username: str) -> TestClient:
        client = TestClient(app)
        response = client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": "test-password"},
        )
        assert response.status_code == 200
        client.headers["X-CSRF-Token"] = client.cookies.get("uveitis_csrf")
        return client

    doctor_a = login("doctor-a")
    doctor_b = login("doctor-b")
    admin = TestClient(app)
    admin_login = admin.post(
        "/api/v1/auth/admin/login",
        json={"username": ROOT_ADMIN_USERNAME, "password": "test-password"},
    )
    assert admin_login.status_code == 200
    admin.headers["X-CSRF-Token"] = admin.cookies.get("uveitis_csrf")

    for doctor in (doctor_a, doctor_b):
        created = doctor.post(
            "/api/v1/cases",
            json={
                "patient_age": 34,
                "patient_sex": "F",
                "complaint": "左眼视物模糊三天",
                "medical_history": "无特殊",
                "affected_eye": "OS",
                "consent_confirmed": True,
            },
        )
        assert created.status_code == 201
        analyzed = doctor.post(f"/api/v1/cases/{created.json()['id']}/analyze")
        assert analyzed.status_code == 202

    admin_view = admin.get("/api/v1/cases/analysis-jobs")
    assert admin_view.status_code == 200
    assert len(admin_view.json()) == 2
    assert {item["owner_name"] for item in admin_view.json()} == {"医生甲", "医生乙"}

    doctor_view = doctor_a.get("/api/v1/cases/analysis-jobs")
    assert doctor_view.status_code == 200
    jobs = doctor_view.json()
    assert len(jobs) == 1
    assert jobs[0]["owner_name"] == "医生甲"
    assert jobs[0]["complaint"] == "左眼视物模糊三天"
    assert jobs[0]["job_status"] in {"queued", "running", "finalizing", "completed"}


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


def test_memory_auth_store_round_trip(tmp_path: Path) -> None:
    app = create_app(
        upload_dir=tmp_path / "uploads",
        vector_dir=tmp_path / "vectors",
        use_environment_database=False,
        user_store=MemoryUserStore(),
        audit_store=MemoryAuthAuditStore(),
        redis_store=MemorySessionStore(),
        bootstrap_users=False,
    )
    password = app.state.auth_service.hash_password("memory-test-password")
    app.state.user_store.ensure_user("memory.doctor", password, "内存医生", "doctor")
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "memory.doctor", "password": "memory-test-password"},
    )
    assert response.status_code == 200
    assert response.json()["user"]["permissions"]


def test_registration_is_not_exposed(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": "self.registered",
            "display_name": "自主注册",
            "password": "self-register-password",
        },
    )
    assert response.status_code == 404


def test_admin_cannot_create_second_admin(tmp_path: Path) -> None:
    client = make_client(tmp_path, role="admin")
    response = client.post(
        "/api/v1/admin/users",
        json={
            "username": "admin.two",
            "display_name": "第二管理员",
            "role": "admin",
            "password": "second-admin-password",
        },
    )
    assert response.status_code == 422


def test_root_admin_cannot_be_disabled_or_reset(tmp_path: Path) -> None:
    client = make_client(tmp_path, role="admin")
    users = client.get("/api/v1/admin/users").json()
    root = next(user for user in users if user["is_root"])

    disabled = client.patch(
        f"/api/v1/admin/users/{root['id']}",
        json={"is_active": False},
    )
    assert disabled.status_code == 409

    reset = client.post(
        f"/api/v1/admin/users/{root['id']}/password",
        json={"new_password": "replacement-password"},
    )
    assert reset.status_code == 409

    self_change = client.post(
        "/api/v1/auth/password",
        json={
            "current_password": "test-password",
            "new_password": "replacement-password",
        },
    )
    assert self_change.status_code == 409


def test_admin_reset_password_revokes_sessions_and_reenables_login(
    tmp_path: Path,
) -> None:
    admin = make_client(tmp_path, role="admin")
    created = admin.post(
        "/api/v1/admin/users",
        json={
            "username": "reset.target",
            "display_name": "重置目标",
            "password": "original-password",
        },
    ).json()

    doctor_client = TestClient(admin.app)
    login = doctor_client.post(
        "/api/v1/auth/login",
        json={"username": "reset.target", "password": "original-password"},
    )
    assert login.status_code == 200
    old_access = doctor_client.cookies.get("uveitis_access")
    old_refresh = doctor_client.cookies.get("uveitis_refresh")
    assert old_access and old_refresh

    reset = admin.post(
        f"/api/v1/admin/users/{created['id']}/password",
        json={"new_password": "replacement-password"},
    )
    assert reset.status_code == 204

    stale_access = TestClient(admin.app)
    stale_access.cookies.set("uveitis_access", old_access, path="/")
    assert stale_access.get("/api/v1/auth/me").status_code == 401

    stale_refresh = TestClient(admin.app)
    stale_refresh.cookies.set("uveitis_refresh", old_refresh, path="/api/v1/auth/refresh")
    stale_refresh.cookies.set("uveitis_csrf", "unused", path="/")
    stale_refresh.headers["X-CSRF-Token"] = "unused"
    assert stale_refresh.post("/api/v1/auth/refresh").status_code == 401

    old_password = TestClient(admin.app)
    assert old_password.post(
        "/api/v1/auth/login",
        json={"username": "reset.target", "password": "original-password"},
    ).status_code == 401

    new_password = TestClient(admin.app)
    relogin = new_password.post(
        "/api/v1/auth/login",
        json={"username": "reset.target", "password": "replacement-password"},
    )
    assert relogin.status_code == 200
    assert relogin.json()["user"]["role"] == "doctor"


def test_concurrent_refresh_reuses_same_tokens(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    old_refresh = client.cookies.get("uveitis_refresh")
    csrf_token = client.cookies.get("uveitis_csrf")
    assert old_refresh and csrf_token

    first = TestClient(client.app)
    first.cookies.set("uveitis_refresh", old_refresh, path="/api/v1/auth/refresh")
    first.cookies.set("uveitis_csrf", csrf_token, path="/")
    first.headers["X-CSRF-Token"] = csrf_token
    first_response = first.post("/api/v1/auth/refresh")
    assert first_response.status_code == 200
    first_access = first_response.cookies.get("uveitis_access")
    first_refresh = first_response.cookies.get("uveitis_refresh")

    second = TestClient(client.app)
    second.cookies.set("uveitis_refresh", old_refresh, path="/api/v1/auth/refresh")
    second.cookies.set("uveitis_csrf", csrf_token, path="/")
    second.headers["X-CSRF-Token"] = csrf_token
    second_response = second.post("/api/v1/auth/refresh")
    assert second_response.status_code == 200
    assert second_response.cookies.get("uveitis_access") == first_access
    assert second_response.cookies.get("uveitis_refresh") == first_refresh

    sessions = first.get("/api/v1/auth/sessions")
    assert sessions.status_code == 200
    assert len(sessions.json()) == 1


def test_parallel_refresh_returns_single_token_pair(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    old_refresh = client.cookies.get("uveitis_refresh")
    csrf_token = client.cookies.get("uveitis_csrf")
    assert old_refresh and csrf_token

    def refresh_once(_: int) -> tuple[int, str | None, str | None]:
        caller = TestClient(client.app)
        caller.cookies.set("uveitis_refresh", old_refresh, path="/api/v1/auth/refresh")
        caller.cookies.set("uveitis_csrf", csrf_token, path="/")
        caller.headers["X-CSRF-Token"] = csrf_token
        response = caller.post("/api/v1/auth/refresh")
        return (
            response.status_code,
            response.cookies.get("uveitis_access"),
            response.cookies.get("uveitis_refresh"),
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(refresh_once, range(4)))

    assert [code for code, _, _ in results] == [200, 200, 200, 200]
    assert len({access for _, access, _ in results}) == 1
    assert len({refresh for _, _, refresh in results}) == 1

    # The pre-refresh access token is retired, so probe with the new one.
    client.cookies.set("uveitis_access", results[0][1], path="/")
    sessions = client.get("/api/v1/auth/sessions")
    assert sessions.status_code == 200
    assert len(sessions.json()) == 1


def test_disabled_doctor_sessions_revoked(tmp_path: Path) -> None:
    admin = make_client(tmp_path, role="admin")
    created = admin.post(
        "/api/v1/admin/users",
        json={
            "username": "disable.target",
            "display_name": "停用目标",
            "password": "disable-password",
        },
    ).json()

    doctor_client = TestClient(admin.app)
    login = doctor_client.post(
        "/api/v1/auth/login",
        json={"username": "disable.target", "password": "disable-password"},
    )
    assert login.status_code == 200
    old_access = doctor_client.cookies.get("uveitis_access")
    old_refresh = doctor_client.cookies.get("uveitis_refresh")
    assert old_access and old_refresh

    disabled = admin.patch(
        f"/api/v1/admin/users/{created['id']}",
        json={"is_active": False},
    )
    assert disabled.status_code == 200

    stale_access = TestClient(admin.app)
    stale_access.cookies.set("uveitis_access", old_access, path="/")
    assert stale_access.get("/api/v1/auth/me").status_code == 401

    stale_refresh = TestClient(admin.app)
    stale_refresh.cookies.set("uveitis_refresh", old_refresh, path="/api/v1/auth/refresh")
    stale_refresh.cookies.set("uveitis_csrf", "unused", path="/")
    stale_refresh.headers["X-CSRF-Token"] = "unused"
    assert stale_refresh.post("/api/v1/auth/refresh").status_code == 401


def test_admin_session_uses_short_token_without_refresh(tmp_path: Path) -> None:
    client = make_client(tmp_path, role="admin")
    assert client.cookies.get("uveitis_refresh") is None
    assert client.cookies.get("uveitis_access") is not None
    assert client.get("/api/v1/auth/me").status_code == 200

    refreshed = client.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 401


def test_admin_session_slides_on_each_request(tmp_path: Path) -> None:
    import time as time_module

    client = make_client(tmp_path, role="admin")
    access_token = client.cookies.get("uveitis_access")
    assert access_token

    sessions_before = client.get("/api/v1/auth/sessions").json()
    assert len(sessions_before) == 1
    first_expiry = sessions_before[0]["expires_at"]

    time_module.sleep(1.1)
    client.get("/api/v1/auth/me")

    sessions_after = client.get("/api/v1/auth/sessions").json()
    assert len(sessions_after) == 1
    second_expiry = sessions_after[0]["expires_at"]
    assert second_expiry > first_expiry


def test_admin_access_cookie_follows_short_ttl_and_renews(tmp_path: Path) -> None:
    users = MemoryUserStore()
    sessions = MemorySessionStore()
    app = create_app(
        upload_dir=tmp_path / "uploads",
        vector_dir=tmp_path / "vectors",
        use_environment_database=False,
        user_store=users,
        audit_store=MemoryAuthAuditStore(),
        redis_store=sessions,
        bootstrap_users=False,
    )
    password = app.state.auth_service.hash_password("test-password")
    users.ensure_user("doctor", password, "测试医生", "doctor")
    users.ensure_single_admin(ROOT_ADMIN_USERNAME, password, "测试管理员")
    client = TestClient(app)

    # A doctor session leaves a refresh cookie in the jar that the admin
    # console must not inherit.
    doctor_login = client.post(
        "/api/v1/auth/login",
        json={"username": "doctor", "password": "test-password"},
    )
    assert doctor_login.status_code == 200
    assert client.cookies.get("uveitis_refresh")

    admin_login = client.post(
        "/api/v1/auth/admin/login",
        json={"username": ROOT_ADMIN_USERNAME, "password": "test-password"},
    )
    assert admin_login.status_code == 200

    login_cookies = admin_login.headers.get_list("set-cookie")
    access_headers = [item for item in login_cookies if item.startswith("uveitis_access=")]
    assert access_headers, "admin login must set the access cookie"
    assert "Max-Age=600" in access_headers[0]
    refresh_headers = [item for item in login_cookies if item.startswith("uveitis_refresh=")]
    assert refresh_headers, "admin login must clear the doctor refresh cookie"
    assert "Max-Age=0" in refresh_headers[0]
    assert client.cookies.get("uveitis_refresh") is None

    client.headers["X-CSRF-Token"] = client.cookies.get("uveitis_csrf")
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    renewed = [item for item in me.headers.get_list("set-cookie") if item.startswith("uveitis_access=")]
    assert renewed, "admin activity must re-issue the access cookie"
    assert "Max-Age=600" in renewed[0]

    doctor_client = TestClient(app)
    doctor_client.post(
        "/api/v1/auth/login",
        json={"username": "doctor", "password": "test-password"},
    )
    doctor_me = doctor_client.get("/api/v1/auth/me")
    assert doctor_me.status_code == 200
    doctor_access_headers = [
        item for item in doctor_me.headers.get_list("set-cookie")
        if item.startswith("uveitis_access=")
    ]
    assert doctor_access_headers == []


def test_doctor_login_after_admin_login_keeps_doctor_identity(tmp_path: Path) -> None:
    users = MemoryUserStore()
    sessions = MemorySessionStore()
    app = create_app(
        upload_dir=tmp_path / "uploads",
        vector_dir=tmp_path / "vectors",
        use_environment_database=False,
        user_store=users,
        audit_store=MemoryAuthAuditStore(),
        redis_store=sessions,
        bootstrap_users=False,
    )
    password = app.state.auth_service.hash_password("test-password")
    users.ensure_user("doctor", password, "测试医生", "doctor")
    users.ensure_single_admin(ROOT_ADMIN_USERNAME, password, "测试管理员")
    client = TestClient(app)

    admin_login = client.post(
        "/api/v1/auth/admin/login",
        json={"username": ROOT_ADMIN_USERNAME, "password": "test-password"},
    )
    assert admin_login.status_code == 200
    assert client.get("/api/v1/auth/me").json()["role"] == "admin"

    # Switching roles in the same browser must not leave the admin token in
    # place: the sliding-renewal middleware has to leave a fresh login alone.
    doctor_login = client.post(
        "/api/v1/auth/login",
        json={"username": "doctor", "password": "test-password"},
    )
    assert doctor_login.status_code == 200
    client.headers["X-CSRF-Token"] = client.cookies.get("uveitis_csrf")
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["role"] == "doctor"
    assert me.json()["username"] == "doctor"


def test_admin_active_sessions_shows_users_and_ips(tmp_path: Path) -> None:
    admin = make_client(tmp_path, role="admin")

    doctor_client = TestClient(admin.app)
    login = doctor_client.post(
        "/api/v1/auth/login",
        json={"username": "doctor", "password": "test-password"},
    )
    assert login.status_code == 200

    active = admin.get("/api/v1/admin/active-sessions")
    assert active.status_code == 200
    items = active.json()
    assert len(items) >= 2
    roles = {item["role"] for item in items}
    assert "admin" in roles
    assert "doctor" in roles
    for item in items:
        assert item["username"]
        assert item["session_id"]

    denied = TestClient(admin.app)
    denied.post(
        "/api/v1/auth/login",
        json={"username": "doctor", "password": "test-password"},
    )
    assert denied.get("/api/v1/admin/active-sessions").status_code == 403


def test_bootstrap_creates_only_root_and_demotes_legacy_admin(tmp_path: Path) -> None:
    users = MemoryUserStore()
    users.ensure_user("legacy.admin", "legacy-password", "旧管理员", "admin")
    bootstrap_settings = settings.model_copy(
        update={"bootstrap_admin_password": "bootstrap-password"}
    )
    create_app(
        upload_dir=tmp_path / "uploads",
        vector_dir=tmp_path / "vectors",
        use_environment_database=False,
        user_store=users,
        audit_store=MemoryAuthAuditStore(),
        redis_store=MemorySessionStore(),
        runtime_settings=bootstrap_settings,
        bootstrap_users=True,
    )
    listed = {user.username: user for user in users.list()}
    assert listed[ROOT_ADMIN_USERNAME].role == "admin"
    assert listed[ROOT_ADMIN_USERNAME].is_root is True
    assert listed["legacy.admin"].role == "doctor"
    assert sum(user.role == "admin" for user in users.list()) == 1


def test_existing_root_password_is_only_changed_in_database(tmp_path: Path) -> None:
    users = MemoryUserStore()
    dictionary = MemoryDataDictionaryStore(
        SecretBox("test-integration-master-key-at-least-32-characters")
    )
    users.ensure_single_admin(
        ROOT_ADMIN_USERNAME,
        "original-database-hash",
        "系统管理员",
    )
    changed_settings = settings.model_copy(
        update={"bootstrap_admin_password": "environment-password-ignored"}
    )
    create_app(
        upload_dir=tmp_path / "uploads",
        vector_dir=tmp_path / "vectors",
        use_environment_database=False,
        user_store=users,
        audit_store=MemoryAuthAuditStore(),
        redis_store=MemorySessionStore(),
        runtime_settings=changed_settings,
        bootstrap_users=True,
        data_dictionary_store=dictionary,
    )
    record = users.get_by_username(ROOT_ADMIN_USERNAME)
    assert record is not None
    assert record[1] == ROOT_PASSWORD_SENTINEL
    assert dictionary.get_value("auth", "root.password_hash") == "original-database-hash"

    empty_settings = settings.model_copy(update={"bootstrap_admin_password": ""})
    create_app(
        upload_dir=tmp_path / "uploads",
        vector_dir=tmp_path / "vectors",
        use_environment_database=False,
        user_store=users,
        audit_store=MemoryAuthAuditStore(),
        redis_store=MemorySessionStore(),
        runtime_settings=empty_settings,
        bootstrap_users=True,
        data_dictionary_store=dictionary,
    )
    record = users.get_by_username(ROOT_ADMIN_USERNAME)
    assert record is not None
    assert record[1] == ROOT_PASSWORD_SENTINEL
    assert dictionary.get_value("auth", "root.password_hash") == "original-database-hash"


def test_bootstrap_stores_root_password_as_plain_string(
    tmp_path: Path,
) -> None:
    users = MemoryUserStore()
    dictionary = MemoryDataDictionaryStore(
        SecretBox("test-integration-master-key-at-least-32-characters")
    )
    bootstrap_settings = settings.model_copy(
        update={"bootstrap_admin_password": "root-bootstrap-password"}
    )
    app = create_app(
        upload_dir=tmp_path / "uploads",
        vector_dir=tmp_path / "vectors",
        use_environment_database=False,
        user_store=users,
        audit_store=MemoryAuthAuditStore(),
        redis_store=MemorySessionStore(),
        runtime_settings=bootstrap_settings,
        bootstrap_users=True,
        data_dictionary_store=dictionary,
    )

    record = users.get_by_username(ROOT_ADMIN_USERNAME)
    assert record is not None
    assert record[1] == ROOT_PASSWORD_SENTINEL
    entries = dictionary.list_entries(namespace="auth")
    entry = next(item for item in entries if item.key == "root.password_hash")
    assert entry.value_type == "string"
    assert entry.is_secret is False
    assert entry.value == "root-bootstrap-password"

    client = TestClient(app)
    login = client.post(
        "/api/v1/auth/admin/login",
        json={"username": ROOT_ADMIN_USERNAME, "password": "root-bootstrap-password"},
    )
    assert login.status_code == 200


def test_bootstrap_migrates_legacy_secret_root_password_to_plain_string(
    tmp_path: Path,
) -> None:
    users = MemoryUserStore()
    dictionary = MemoryDataDictionaryStore(
        SecretBox("test-integration-master-key-at-least-32-characters")
    )
    dictionary.set_value(
        "auth",
        "root.password_hash",
        "root-plain-password",
        value_type="secret",
        description="root 管理员密码",
        actor_id="legacy-bootstrap",
    )
    create_app(
        upload_dir=tmp_path / "uploads",
        vector_dir=tmp_path / "vectors",
        use_environment_database=False,
        user_store=users,
        audit_store=MemoryAuthAuditStore(),
        redis_store=MemorySessionStore(),
        runtime_settings=settings,
        bootstrap_users=True,
        data_dictionary_store=dictionary,
    )

    entry = next(
        item
        for item in dictionary.list_entries(namespace="auth")
        if item.key == "root.password_hash"
    )
    assert entry.value_type == "string"
    assert entry.is_secret is False
    assert entry.value == "root-plain-password"


def test_data_dictionary_api_is_admin_only_and_redacts_secrets(tmp_path: Path) -> None:
    doctor = make_client(tmp_path)
    assert doctor.get("/api/v1/admin/data-dictionary").status_code == 403

    admin = make_client(tmp_path, role="admin")
    created = admin.patch(
        "/api/v1/admin/integrations",
        json={
            "summary_api_key": "dictionary-secret-value",
            "expected_revision": 0,
        },
    )
    assert created.status_code == 200

    entries = admin.get(
        "/api/v1/admin/data-dictionary",
        params={"namespace": "integration"},
    )
    assert entries.status_code == 200
    secret = next(
        item for item in entries.json() if item["key"] == "summary.api_key"
    )
    assert secret["configured"] is True
    assert secret["value"] is None
    assert "dictionary-secret-value" not in entries.text

    protected = admin.put(
        "/api/v1/admin/data-dictionary/integration/summary.api_key",
        json={"value": "replacement", "expected_revision": secret["revision"]},
    )
    assert protected.status_code == 409

    writable = admin.put(
        "/api/v1/admin/data-dictionary/runtime/sample.flag",
        json={"value": True, "value_type": "bool", "description": "接口测试项"},
    )
    assert writable.status_code == 200
    assert writable.json()["value"] is True

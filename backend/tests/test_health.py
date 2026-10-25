from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app
from app.db.users import MemoryUserStore
from app.services.redis_store import MemorySessionStore


def make_client(tmp_path: Path) -> TestClient:
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
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "doctor", "password": "test-password"},
    )
    assert login.status_code == 200
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

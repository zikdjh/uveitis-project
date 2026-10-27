from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.auth_policy import ROOT_ADMIN_DISPLAY_NAME, ROOT_ADMIN_USERNAME
from app.core.config import settings
from app.db import PostgresCaseStore
from app.db.audit import AuthAuditStore
from app.db.users import UserStore
from app.routers import admin, auth, cases, health, integrations, knowledge, system
from app.services import (
    AnalysisService,
    AuthService,
    KnowledgeStore,
    OptionalIntegrations,
    RedisStore,
)
from app.services.integration_settings import (
    MemoryIntegrationSettingsStore,
    PostgresIntegrationSettingsStore,
    SecretBox,
)


class MemoryCaseStore:
    """In-process case repository for isolated application tests."""

    def __init__(self) -> None:
        self._cases = {}

    def save(self, case):
        self._cases[case.id] = case
        return case

    def get(self, case_id):
        return self._cases.get(case_id)

    def list(self, limit: int = 100):
        return sorted(
            self._cases.values(),
            key=lambda case: case.updated_at,
            reverse=True,
        )[:limit]

    def stats(self):
        from app.schemas.case import CaseStats

        counts = {"analyzing": 0, "awaiting_review": 0, "reviewed": 0}
        for case in self._cases.values():
            if case.status in counts:
                counts[case.status] += 1
        return CaseStats(total=len(self._cases), **counts)


def create_app(
    *,
    upload_dir: Path | None = None,
    vector_dir: Path | None = None,
    database_url: str | None = None,
    use_environment_database: bool = True,
    redis_store=None,
    user_store=None,
    audit_store=None,
    bootstrap_users: bool = True,
    runtime_settings=None,
) -> FastAPI:
    runtime_settings = runtime_settings or settings
    app = FastAPI(
        title=runtime_settings.app_name,
        version=runtime_settings.app_version,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=runtime_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if request.url.path.startswith("/api/v1/auth") or request.url.path.startswith("/api/v1/admin"):
            response.headers["Cache-Control"] = "no-store"
        return response

    resolved_upload_dir = upload_dir or runtime_settings.upload_dir
    resolved_upload_dir.mkdir(parents=True, exist_ok=True)
    app.state.settings = runtime_settings
    app.state.upload_dir = resolved_upload_dir
    resolved_database_url = database_url
    if resolved_database_url is None and use_environment_database:
        resolved_database_url = runtime_settings.database_url or None
    if resolved_database_url:
        case_store = PostgresCaseStore(
            resolved_database_url,
            runtime_settings.database_connect_timeout_seconds,
        )
    else:
        if use_environment_database:
            raise RuntimeError("服务必须配置 APP_DATABASE_URL 并使用 PostgreSQL")
        case_store = MemoryCaseStore()
    app.state.case_store = case_store
    app.state.redis_store = redis_store or RedisStore(runtime_settings.redis_url)
    if user_store is not None:
        app.state.user_store = user_store
    elif not use_environment_database:
        from app.db.users import MemoryUserStore

        app.state.user_store = MemoryUserStore()
    else:
        app.state.user_store = UserStore(case_store._session_factory)
    if audit_store is not None:
        app.state.audit_store = audit_store
    elif not use_environment_database:
        from app.db.audit import MemoryAuthAuditStore

        app.state.audit_store = MemoryAuthAuditStore()
    else:
        app.state.audit_store = AuthAuditStore(case_store._session_factory)
    app.state.auth_service = AuthService(
        app.state.user_store,
        app.state.redis_store,
        runtime_settings.access_token_ttl_seconds,
        runtime_settings.refresh_token_ttl_seconds,
        refresh_grace_seconds=runtime_settings.refresh_rotation_grace_seconds,
        login_max_attempts=runtime_settings.login_max_attempts,
        login_window_seconds=runtime_settings.login_window_seconds,
    )
    if bootstrap_users:
        _bootstrap_root_admin(app.state.auth_service, runtime_settings)
    app.state.knowledge_store = KnowledgeStore(
        runtime_settings,
        vector_dir or runtime_settings.vector_dir,
    )
    secret_material = runtime_settings.integration_secret_key or (
        "development-only-integration-secret-change-me"
    )
    if (
        not runtime_settings.integration_secret_key
        and runtime_settings.environment.lower() not in {"development", "test"}
    ):
        raise RuntimeError(
            "生产环境必须配置 APP_INTEGRATION_SECRET_KEY（至少 32 个字符）"
        )
    secret_box = SecretBox(secret_material)
    if not use_environment_database:
        app.state.integration_settings_store = MemoryIntegrationSettingsStore(
            secret_box
        )
    else:
        app.state.integration_settings_store = PostgresIntegrationSettingsStore(
            case_store._session_factory,
            secret_box,
        )
    app.state.integrations = OptionalIntegrations(
        runtime_settings,
        config_store=app.state.integration_settings_store,
    )
    app.state.analysis_service = AnalysisService(
        runtime_settings,
        knowledge_store=app.state.knowledge_store,
        integrations=app.state.integrations,
    )

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(admin.router)
    app.include_router(integrations.router)
    app.include_router(cases.router)
    app.include_router(system.router)
    app.include_router(knowledge.router)

    @app.get("/")
    def root() -> dict[str, str]:
        return {
            "service": runtime_settings.app_name,
            "version": runtime_settings.app_version,
            "docs": "/docs",
        }

    return app


class _UnavailableUserStore:
    def get_by_username(self, username):
        return None

    def get(self, user_id):
        return None


def _bootstrap_root_admin(auth_service: AuthService, config) -> None:
    existing = auth_service.users.get_by_username(ROOT_ADMIN_USERNAME)
    if existing is None and not config.bootstrap_admin_password:
        raise RuntimeError(
            "root 管理员首次创建必须配置 APP_BOOTSTRAP_ADMIN_PASSWORD"
        )
    auth_service.users.ensure_single_admin(
        ROOT_ADMIN_USERNAME,
        (
            auth_service.hash_password(config.bootstrap_admin_password)
            if config.bootstrap_admin_password
            else None
        ),
        ROOT_ADMIN_DISPLAY_NAME,
    )

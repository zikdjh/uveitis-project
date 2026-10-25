from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.db import CaseStore, PostgresCaseStore
from app.db.users import UserStore
from app.routers import auth, cases, health, knowledge, system
from app.services import (
    AnalysisService,
    AuthService,
    KnowledgeStore,
    RedisStore,
)


def create_app(
    *,
    database_path: Path | None = None,
    upload_dir: Path | None = None,
    vector_dir: Path | None = None,
    database_url: str | None = None,
    use_environment_database: bool = True,
    redis_store=None,
    user_store=None,
    bootstrap_users: bool = True,
) -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    resolved_upload_dir = upload_dir or settings.upload_dir
    resolved_upload_dir.mkdir(parents=True, exist_ok=True)
    app.state.settings = settings
    app.state.upload_dir = resolved_upload_dir
    resolved_database_url = database_url
    if resolved_database_url is None and use_environment_database:
        resolved_database_url = settings.database_url or None
    if resolved_database_url:
        case_store = PostgresCaseStore(resolved_database_url)
    else:
        case_store = CaseStore(database_path or settings.database_path)
    app.state.case_store = case_store
    app.state.redis_store = redis_store or RedisStore(settings.redis_url)
    if user_store is not None:
        app.state.user_store = user_store
    elif hasattr(case_store, "_session_factory"):
        app.state.user_store = UserStore(case_store._session_factory)
    else:
        app.state.user_store = _UnavailableUserStore()
    app.state.auth_service = AuthService(
        app.state.user_store,
        app.state.redis_store,
        settings.session_ttl_seconds,
    )
    if bootstrap_users:
        _bootstrap_users(app.state.auth_service, settings)
    app.state.analysis_service = AnalysisService(settings)
    app.state.knowledge_store = KnowledgeStore(
        settings,
        vector_dir or settings.vector_dir,
    )

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(cases.router)
    app.include_router(system.router)
    app.include_router(knowledge.router)

    @app.get("/")
    def root() -> dict[str, str]:
        return {
            "service": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs",
        }

    return app


class _UnavailableUserStore:
    def get_by_username(self, username):
        return None

    def get(self, user_id):
        return None


def _bootstrap_users(auth_service: AuthService, config) -> None:
    for username, password, display_name, role in (
        (
            config.bootstrap_doctor_username,
            config.bootstrap_doctor_password,
            "示例医生",
            "doctor",
        ),
        (
            config.bootstrap_admin_username,
            config.bootstrap_admin_password,
            "系统管理员",
            "admin",
        ),
    ):
        if username and password:
            auth_service.users.ensure_user(
                username,
                auth_service.hash_password(password),
                display_name,
                role,
            )


app = create_app()

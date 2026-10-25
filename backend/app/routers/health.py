from fastapi import APIRouter, Request

from app.core.config import settings


router = APIRouter(prefix="/api/v1/health", tags=["health"])


@router.get("")
def health(request: Request) -> dict[str, str | bool]:
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "ready": request.app.state.case_store is not None,
    }

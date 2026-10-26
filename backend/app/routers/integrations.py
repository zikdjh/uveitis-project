from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.core.security import request_ip, request_user_agent, require_permission
from app.schemas.auth import Permission
from app.schemas.integrations import (
    IntegrationConfigRead,
    IntegrationConfigTestBatchRequest,
    IntegrationConfigTestBatchResult,
    IntegrationConfigTestRequest,
    IntegrationConfigTestResult,
    IntegrationConfigUpdate,
)


router = APIRouter(prefix="/api/v1/admin/integrations", tags=["integrations"])


def _audit(request: Request, actor, detail: str) -> None:
    request.app.state.audit_store.record(
        event="integration_config_update",
        outcome="success",
        username=actor.username,
        user_id=actor.id,
        actor_id=actor.id,
        ip_address=request_ip(request),
        user_agent=request_user_agent(request),
        detail=detail,
    )


@router.get("", response_model=IntegrationConfigRead)
def get_config(request: Request) -> IntegrationConfigRead:
    require_permission(request, Permission.INTEGRATION_READ)
    return request.app.state.integrations.public_config()


@router.get("/status")
def get_status(request: Request) -> dict[str, dict[str, bool]]:
    require_permission(request, Permission.SYSTEM_READ)
    config = request.app.state.integrations.public_config()
    return {
        "summary": {"enabled": config.summary_enabled},
        "search": {"enabled": config.web_search_enabled},
    }


@router.patch("", response_model=IntegrationConfigRead)
def update_config(payload: IntegrationConfigUpdate, request: Request) -> IntegrationConfigRead:
    actor = require_permission(request, Permission.INTEGRATION_MANAGE)
    try:
        updated = request.app.state.integration_settings_store.update(
            payload,
            actor_id=actor.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _audit(request, actor, f"更新外部服务配置，revision={updated.revision}")
    return updated


@router.post("/test", response_model=IntegrationConfigTestResult)
def test_config(payload: IntegrationConfigTestRequest, request: Request) -> IntegrationConfigTestResult:
    require_permission(request, Permission.INTEGRATION_MANAGE)
    outcome = (
        request.app.state.integrations.test_search(payload.provider, payload.query)
        if payload.kind == "search"
        else request.app.state.integrations.test_summary()
    )
    return IntegrationConfigTestResult(**outcome.__dict__)


@router.post("/test-search-batch", response_model=IntegrationConfigTestBatchResult)
def test_search_batch(
    payload: IntegrationConfigTestBatchRequest, request: Request
) -> IntegrationConfigTestBatchResult:
    require_permission(request, Permission.INTEGRATION_MANAGE)
    if not payload.providers:
        return IntegrationConfigTestBatchResult(
            ok=False,
            failed=0,
            items=[
                IntegrationConfigTestResult(
                    ok=False,
                    detail="没有已配置连接凭据的搜索服务商",
                    latency_ms=0,
                )
            ],
        )
    items = [
        IntegrationConfigTestResult(
            **request.app.state.integrations.test_search(provider, payload.query).__dict__
        )
        for provider in payload.providers
    ]
    succeeded = sum(1 for item in items if item.ok)
    return IntegrationConfigTestBatchResult(
        ok=succeeded > 0,
        succeeded=succeeded,
        failed=sum(1 for item in items if not item.ok),
        items=items,
    )

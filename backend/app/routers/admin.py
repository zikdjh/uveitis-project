from __future__ import annotations

from datetime import UTC, datetime, time, timedelta

from fastapi import APIRouter, HTTPException, Query, Request, Response, status

from app.core.auth_policy import ROOT_ADMIN_USERNAME
from app.core.security import (
    request_ip,
    request_user_agent,
    require_permission,
)
from app.schemas.auth import (
    AuthAuditEventPage,
    PasswordReset,
    Permission,
    UserCreate,
    UserRead,
    UserUpdate,
)


router = APIRouter(prefix="/api/v1/admin", tags=["administration"])

AUDIT_EVENTS = {
    "login",
    "doctor_login",
    "admin_login",
    "token_refresh",
    "logout",
    "session_revoke",
    "session_revoke_others",
    "password_change",
    "password_reset",
    "user_create",
    "user_update",
    "integration_config_update",
}
AUDIT_OUTCOMES = {"success", "failed", "blocked"}


def _audit(
    request: Request,
    *,
    event: str,
    outcome: str,
    username: str,
    user_id: str | None = None,
    actor_id: str | None = None,
    detail: str = "",
) -> None:
    request.app.state.audit_store.record(
        event=event,
        outcome=outcome,
        username=username,
        user_id=user_id,
        actor_id=actor_id,
        ip_address=request_ip(request),
        user_agent=request_user_agent(request),
        detail=detail,
    )


@router.get("/users", response_model=list[UserRead])
def list_users(request: Request) -> list[UserRead]:
    require_permission(request, Permission.USER_READ)
    return request.app.state.user_store.list()


@router.post("/users", response_model=UserRead, status_code=201)
def create_user(payload: UserCreate, request: Request) -> UserRead:
    actor = require_permission(request, Permission.USER_MANAGE)
    auth = request.app.state.auth_service
    if payload.username.strip().lower() == ROOT_ADMIN_USERNAME:
        raise HTTPException(status_code=409, detail="root 管理员账号已由系统保留")
    try:
        user = auth.users.create(
            payload.username,
            auth.hash_password(payload.password),
            payload.display_name,
            "doctor",
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _audit(
        request,
        event="user_create",
        outcome="success",
        username=user.username,
        user_id=user.id,
        actor_id=actor.id,
        detail="管理员创建医生账号",
    )
    return user


@router.patch("/users/{user_id}", response_model=UserRead)
def update_user(user_id: str, payload: UserUpdate, request: Request) -> UserRead:
    actor = require_permission(request, Permission.USER_MANAGE)
    users = request.app.state.user_store
    current = users.get(user_id)
    if current is None:
        raise HTTPException(status_code=404, detail="账号不存在")

    next_active = current.is_active if payload.is_active is None else payload.is_active
    if current.username == ROOT_ADMIN_USERNAME and next_active is False:
        raise HTTPException(status_code=409, detail="固定管理员账号不能停用")
    if current.id == actor.id and next_active is False:
        raise HTTPException(status_code=409, detail="不能停用当前登录账号")

    updated = users.update(
        user_id,
        display_name=payload.display_name,
        is_active=payload.is_active,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="账号不存在")
    if not updated.is_active:
        request.app.state.auth_service.revoke_all_sessions(updated.id)
    _audit(
        request,
        event="user_update",
        outcome="success",
        username=updated.username,
        user_id=updated.id,
        actor_id=actor.id,
        detail=f"账号状态 {'启用' if updated.is_active else '停用'}",
    )
    return updated


@router.post("/users/{user_id}/password", status_code=204)
def reset_password(
    user_id: str,
    payload: PasswordReset,
    request: Request,
) -> Response:
    actor = require_permission(request, Permission.USER_MANAGE)
    auth = request.app.state.auth_service
    user = request.app.state.user_store.get(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="账号不存在")
    if user.username == ROOT_ADMIN_USERNAME:
        raise HTTPException(status_code=409, detail="固定管理员账号密码不能由后台重置")
    auth.users.set_password(user.id, auth.hash_password(payload.new_password))
    auth.revoke_all_sessions(user.id)
    _audit(
        request,
        event="password_reset",
        outcome="success",
        username=user.username,
        user_id=user.id,
        actor_id=actor.id,
        detail="管理员重置密码并撤销全部会话",
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _audit_date_bounds(from_date: str | None, to_date: str | None):
    try:
        start = (
            datetime.combine(datetime.fromisoformat(from_date).date(), time.min, UTC)
            if from_date
            else None
        )
        end = (
            datetime.combine(
                datetime.fromisoformat(to_date).date() + timedelta(days=1),
                time.min,
                UTC,
            )
            if to_date
            else None
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="日期格式应为 YYYY-MM-DD") from exc
    if start and end and start >= end:
        raise HTTPException(status_code=422, detail="开始日期不能晚于结束日期")
    return start, end


@router.get("/audit-events", response_model=AuthAuditEventPage)
def list_audit_events(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    event: str | None = Query(default=None, max_length=50),
    outcome: str | None = Query(default=None, max_length=30),
    from_date: str | None = Query(default=None, alias="from"),
    to_date: str | None = Query(default=None, alias="to"),
    search: str | None = Query(default=None, max_length=100),
) -> AuthAuditEventPage:
    require_permission(request, Permission.AUDIT_READ)
    if event and event not in AUDIT_EVENTS:
        raise HTTPException(status_code=422, detail="不支持的审计事件")
    if outcome and outcome not in AUDIT_OUTCOMES:
        raise HTTPException(status_code=422, detail="不支持的审计结果")
    from_at, to_at = _audit_date_bounds(from_date, to_date)
    items, total = request.app.state.audit_store.list_page(
        page=page,
        page_size=page_size,
        event=event,
        outcome=outcome,
        from_at=from_at,
        to_at=to_at,
        search=search,
    )
    return AuthAuditEventPage(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )

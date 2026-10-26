from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, Response, status

from app.core.security import (
    request_ip,
    request_user_agent,
    require_permission,
)
from app.schemas.auth import (
    AuthAuditEventRead,
    PasswordReset,
    Permission,
    UserCreate,
    UserRead,
    UserUpdate,
)


router = APIRouter(prefix="/api/v1/admin", tags=["administration"])


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
    try:
        user = auth.users.create(
            payload.username,
            auth.hash_password(payload.password),
            payload.display_name,
            payload.role,
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
        detail=f"创建 {user.role} 账号",
    )
    return user


@router.patch("/users/{user_id}", response_model=UserRead)
def update_user(user_id: str, payload: UserUpdate, request: Request) -> UserRead:
    actor = require_permission(request, Permission.USER_MANAGE)
    users = request.app.state.user_store
    current = users.get(user_id)
    if current is None:
        raise HTTPException(status_code=404, detail="账号不存在")

    next_role = payload.role or current.role
    next_active = current.is_active if payload.is_active is None else payload.is_active
    removes_admin = current.role == "admin" and (
        next_role != "admin" or next_active is False
    )
    if removes_admin and users.count_active_admins(excluding_user_id=current.id) == 0:
        raise HTTPException(status_code=409, detail="系统必须保留至少一个启用的管理员")
    if current.id == actor.id and next_active is False:
        raise HTTPException(status_code=409, detail="不能停用当前登录账号")

    updated = users.update(
        user_id,
        display_name=payload.display_name,
        role=payload.role,
        is_active=payload.is_active,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="账号不存在")
    if not updated.is_active or updated.role != current.role:
        request.app.state.auth_service.revoke_all_sessions(updated.id)
    _audit(
        request,
        event="user_update",
        outcome="success",
        username=updated.username,
        user_id=updated.id,
        actor_id=actor.id,
        detail=f"角色 {updated.role}，状态 {'启用' if updated.is_active else '停用'}",
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


@router.get("/audit-events", response_model=list[AuthAuditEventRead])
def list_audit_events(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[AuthAuditEventRead]:
    require_permission(request, Permission.AUDIT_READ)
    return request.app.state.audit_store.list(limit=limit)

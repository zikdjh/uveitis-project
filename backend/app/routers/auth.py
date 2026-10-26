from __future__ import annotations

from secrets import token_urlsafe

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from app.core.security import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    REFRESH_COOKIE,
    current_user,
    request_ip,
    request_user_agent,
    require_user,
    validate_csrf,
)
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    PasswordChange,
    SessionRead,
    UserRead,
)
from app.services.auth import SessionTokens


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


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


def _set_auth_cookies(
    response: Response,
    *,
    request: Request,
    tokens: SessionTokens,
    csrf_token: str,
) -> None:
    settings = request.app.state.settings
    auth = request.app.state.auth_service
    response.set_cookie(
        ACCESS_COOKIE,
        tokens.access_token,
        max_age=auth.access_ttl_seconds,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        tokens.refresh_token,
        max_age=auth.refresh_ttl_seconds,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/api/v1/auth/refresh",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        max_age=auth.refresh_ttl_seconds,
        httponly=False,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth/refresh")
    response.delete_cookie(CSRF_COOKIE, path="/")


def _unauthorized_response(detail: str = "登录状态已失效") -> JSONResponse:
    response = JSONResponse({"detail": detail}, status_code=401)
    _clear_auth_cookies(response)
    return response


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request) -> Response:
    auth = request.app.state.auth_service
    username = payload.username.strip().lower()
    identity = f"{username}:{request_ip(request)}"
    if not auth.login_allowed(identity):
        _audit(
            request,
            event="login",
            outcome="blocked",
            username=username,
            detail="登录失败次数过多",
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="登录失败次数过多，请稍后重试",
            headers={"Retry-After": str(auth.login_window_seconds)},
        )

    user = auth.authenticate(username, payload.password)
    if user is None:
        failures = auth.record_login_failure(identity)
        _audit(
            request,
            event="login",
            outcome="failure",
            username=username,
            detail=f"凭据不正确或账号已停用（连续失败 {failures} 次）",
        )
        raise HTTPException(status_code=401, detail="用户名或密码不正确")

    auth.clear_login_failures(identity)
    tokens, result = auth.create_session(
        user,
        ip_address=request_ip(request),
        user_agent=request_user_agent(request),
    )
    response = JSONResponse(result.model_dump(mode="json"))
    _set_auth_cookies(
        response,
        request=request,
        tokens=tokens,
        csrf_token=token_urlsafe(32),
    )
    _audit(
        request,
        event="login",
        outcome="success",
        username=user.username,
        user_id=user.id,
        detail=f"角色 {user.role}",
    )
    return response


@router.post("/refresh", response_model=LoginResponse)
def refresh(request: Request) -> Response:
    validate_csrf(request)
    refresh_token = request.cookies.get(REFRESH_COOKIE)
    if not refresh_token:
        return _unauthorized_response()
    result = request.app.state.auth_service.refresh_session(
        refresh_token,
        ip_address=request_ip(request),
        user_agent=request_user_agent(request),
    )
    if result is None:
        _audit(
            request,
            event="token_refresh",
            outcome="failure",
            username="",
            detail="刷新令牌无效或已过期",
        )
        return _unauthorized_response()

    tokens, login_response = result
    response = JSONResponse(login_response.model_dump(mode="json"))
    _set_auth_cookies(
        response,
        request=request,
        tokens=tokens,
        csrf_token=token_urlsafe(32),
    )
    _audit(
        request,
        event="token_refresh",
        outcome="success",
        username=login_response.user.username,
        user_id=login_response.user.id,
        detail="访问令牌与刷新令牌已轮换",
    )
    return response


@router.get("/me", response_model=UserRead)
def me(request: Request, response: Response) -> UserRead:
    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="请先登录")
    if not request.cookies.get(CSRF_COOKIE):
        response.set_cookie(
            CSRF_COOKIE,
            token_urlsafe(32),
            max_age=request.app.state.auth_service.refresh_ttl_seconds,
            httponly=False,
            samesite="lax",
            secure=request.app.state.settings.cookie_secure,
            path="/",
        )
    return user


@router.post("/logout", status_code=204)
def logout(request: Request) -> Response:
    validate_csrf(request)
    auth = request.app.state.auth_service
    access_token = request.cookies.get(ACCESS_COOKIE)
    refresh_token = request.cookies.get(REFRESH_COOKIE)
    user = current_user(request)
    if user is None:
        user = auth.session_user(refresh_token) if refresh_token else None
    auth.logout(
        access_token=access_token,
        refresh_token=refresh_token,
        user_id=user.id if user else None,
    )
    if user is not None:
        _audit(
            request,
            event="logout",
            outcome="success",
            username=user.username,
            user_id=user.id,
        )
    response = Response(status_code=204)
    _clear_auth_cookies(response)
    return response


@router.get("/sessions", response_model=list[SessionRead])
def list_sessions(request: Request) -> list[SessionRead]:
    user = require_user(request)
    access_token = request.cookies.get(ACCESS_COOKIE, "")
    return request.app.state.auth_service.list_sessions(user.id, access_token)


@router.delete("/sessions/{session_id}", status_code=204)
def revoke_session(session_id: str, request: Request) -> Response:
    user = require_user(request)
    auth = request.app.state.auth_service
    current_session_id = auth.current_session_id(
        request.cookies.get(ACCESS_COOKIE, "")
    )
    if session_id == current_session_id:
        raise HTTPException(status_code=409, detail="当前会话请使用退出登录")
    if not auth.revoke_session(user.id, session_id):
        raise HTTPException(status_code=404, detail="会话不存在或已失效")
    _audit(
        request,
        event="session_revoke",
        outcome="success",
        username=user.username,
        user_id=user.id,
        actor_id=user.id,
        detail=f"撤销会话 {session_id[:12]}",
    )
    return Response(status_code=204)


@router.post("/sessions/revoke-others", status_code=204)
def revoke_other_sessions(request: Request) -> Response:
    user = require_user(request)
    access_token = request.cookies.get(ACCESS_COOKIE, "")
    count = request.app.state.auth_service.revoke_other_sessions(user.id, access_token)
    _audit(
        request,
        event="session_revoke_others",
        outcome="success",
        username=user.username,
        user_id=user.id,
        actor_id=user.id,
        detail=f"撤销 {count} 个其他会话",
    )
    return Response(status_code=204)


@router.post("/password", status_code=204)
def change_password(payload: PasswordChange, request: Request) -> Response:
    user = require_user(request)
    auth = request.app.state.auth_service
    if not auth.verify_password(user.id, payload.current_password):
        _audit(
            request,
            event="password_change",
            outcome="failure",
            username=user.username,
            user_id=user.id,
            actor_id=user.id,
            detail="当前密码校验失败",
        )
        raise HTTPException(status_code=400, detail="当前密码不正确")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=422, detail="新密码不能与当前密码相同")
    auth.users.set_password(user.id, auth.hash_password(payload.new_password))
    access_token = request.cookies.get(ACCESS_COOKIE, "")
    auth.revoke_other_sessions(user.id, access_token)
    _audit(
        request,
        event="password_change",
        outcome="success",
        username=user.username,
        user_id=user.id,
        actor_id=user.id,
        detail="账号密码已更新，其他会话已撤销",
    )
    return Response(status_code=204)

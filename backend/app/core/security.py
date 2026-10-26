from __future__ import annotations

from hmac import compare_digest

from fastapi import HTTPException, Request, status

from app.schemas.auth import Permission, ROLE_PERMISSIONS, UserRead, UserRole


ACCESS_COOKIE = "uveitis_access"
REFRESH_COOKIE = "uveitis_refresh"
CSRF_COOKIE = "uveitis_csrf"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def current_user(request: Request) -> UserRead | None:
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        return None
    return request.app.state.auth_service.current_user(token)


def require_user(request: Request) -> UserRead:
    user = current_user(request)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录",
        )
    validate_csrf(request)
    return user


def require_role(request: Request, *roles: UserRole) -> UserRead:
    user = require_user(request)
    if user.role not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="当前账号无权执行此操作",
        )
    return user


def require_permission(request: Request, *permissions: Permission) -> UserRead:
    user = require_user(request)
    granted = ROLE_PERMISSIONS[user.role]
    if not all(permission in granted for permission in permissions):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="当前账号缺少所需权限",
        )
    return user


def validate_csrf(request: Request) -> None:
    if request.method.upper() in SAFE_METHODS:
        return
    cookie_token = request.cookies.get(CSRF_COOKIE, "")
    header_token = request.headers.get(CSRF_HEADER, "")
    if not cookie_token or not header_token or not compare_digest(cookie_token, header_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="安全校验失败，请刷新页面后重试",
        )


def request_ip(request: Request) -> str:
    if request.app.state.settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else ""


def request_user_agent(request: Request) -> str:
    return request.headers.get("user-agent", "")

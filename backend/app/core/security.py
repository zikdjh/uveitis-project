from fastapi import HTTPException, Request, status

from app.schemas.auth import UserRead, UserRole


def current_user(request: Request) -> UserRead | None:
    token = request.cookies.get("uveitis_session")
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
    return user


def require_role(request: Request, *roles: UserRole) -> UserRead:
    user = require_user(request)
    if user.role not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="当前账号无权执行此操作",
        )
    return user

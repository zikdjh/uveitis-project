from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from app.core.security import current_user
from app.schemas.auth import LoginRequest, LoginResponse, UserRead


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
SESSION_COOKIE = "uveitis_session"


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request) -> Response:
    auth = request.app.state.auth_service
    user = auth.authenticate(payload.username, payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="用户名或密码不正确")
    token, result = auth.create_session(user)
    response = JSONResponse(result.model_dump(mode="json"))
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=auth.ttl_seconds,
        httponly=True,
        samesite="lax",
        secure=request.app.state.settings.cookie_secure,
        path="/",
    )
    return response


@router.get("/me", response_model=UserRead)
def me(request: Request) -> UserRead:
    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="请先登录")
    return user


@router.post("/logout", status_code=204)
def logout(request: Request) -> Response:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        request.app.state.auth_service.logout(token)
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response

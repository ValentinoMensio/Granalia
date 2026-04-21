from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from ...dependencies import get_auth_manager, require_authenticated
from ...schemas import AuthSessionOut


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/session", response_model=AuthSessionOut)
def session_status(request: Request) -> AuthSessionOut:
    auth_manager = get_auth_manager()
    token = request.cookies.get(auth_manager.cookie_name)
    payload = auth_manager.verify_session_token(token)
    if not payload:
        return AuthSessionOut(authenticated=False)
    return AuthSessionOut(authenticated=True, username=str(payload["sub"]))


class LoginPayload(BaseModel):
    username: str
    password: str


@router.post("/login", response_model=AuthSessionOut)
def login(payload: LoginPayload, request: Request, response: Response) -> AuthSessionOut:
    auth_manager = get_auth_manager()
    client_id = request.client.host if request.client else "unknown"
    allowed, retry_after = auth_manager.ensure_login_allowed(client_id)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Demasiados intentos. Reintentá en {retry_after}s.",
        )

    user = auth_manager.verify_credentials(payload.username, payload.password)
    if not user:
        auth_manager.register_failed_login(client_id)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas")

    auth_manager.register_successful_login(client_id)
    token = auth_manager.create_session_token(user)
    response.set_cookie(auth_manager.cookie_name, token, **auth_manager.auth_cookie_settings())
    return AuthSessionOut(authenticated=True, username=user.username)


@router.post("/logout", response_model=AuthSessionOut)
def logout(response: Response, _: str = Depends(require_authenticated)) -> AuthSessionOut:
    auth_manager = get_auth_manager()
    response.delete_cookie(auth_manager.cookie_name, path="/")
    return AuthSessionOut(authenticated=False)

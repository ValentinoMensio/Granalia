from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException, Request, status

from .core.security import AuthManager
from .core.security import SessionTokenPayload
from .infrastructure.postgres import PostgresRepository


CSRF_PROTECTED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _resolve_base_dir() -> Path:
    current = Path(__file__).resolve()
    for candidate in current.parents:
        if (candidate / "img").exists():
            return candidate
    return current.parents[1]


BASE_DIR = _resolve_base_dir()


@lru_cache
def get_repository() -> PostgresRepository:
    return PostgresRepository(BASE_DIR)


@lru_cache
def get_auth_manager() -> AuthManager:
    return AuthManager(BASE_DIR)


def require_session_payload(request: Request) -> SessionTokenPayload:
    cached_payload = getattr(request.state, "auth_payload", None)
    if cached_payload:
        return cached_payload

    auth_manager = get_auth_manager()
    token = request.cookies.get(auth_manager.cookie_name)
    payload = auth_manager.verify_session_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Autenticación requerida")
    if request.method.upper() in CSRF_PROTECTED_METHODS:
        csrf_token = request.headers.get("X-CSRF-Token")
        if not auth_manager.verify_csrf_token(payload, csrf_token):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token CSRF inválido")
    request.state.auth_payload = payload
    return payload


def require_authenticated(request: Request) -> str:
    payload = require_session_payload(request)
    return str(payload["sub"])


def require_admin(request: Request) -> str:
    payload = require_session_payload(request)
    if payload.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permisos de administrador requeridos")
    return str(payload["sub"])


def validate_invoice_authorization_password(password: str) -> None:
    password_hash = os.getenv("GRANALIA_INVOICE_AUTH_PASSWORD_HASH", "").strip()
    if not password_hash:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Contraseña de autorización no configurada")
    if not AuthManager.verify_password(password, password_hash):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Contraseña de autorización inválida")


def current_role(request: Request) -> str:
    return str(require_session_payload(request).get("role") or "operator")

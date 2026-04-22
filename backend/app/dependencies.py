from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException, Request, status

from .core.security import AuthManager
from .infrastructure.postgres import PostgresRepository


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


def require_authenticated(request: Request) -> str:
    auth_manager = get_auth_manager()
    token = request.cookies.get(auth_manager.cookie_name)
    payload = auth_manager.verify_session_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Autenticación requerida")
    return str(payload["sub"])

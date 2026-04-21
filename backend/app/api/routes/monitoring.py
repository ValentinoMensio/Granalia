from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy import select

from ...core.config import load_config
from ...dependencies import get_auth_manager, get_repository
from ...schemas import HealthOut


router = APIRouter(tags=["monitoring"])


@router.get("/health/live", response_model=HealthOut)
def live() -> HealthOut:
    return HealthOut(status="ok")


@router.get("/health/ready")
def ready() -> dict[str, object]:
    config = load_config()
    repository = get_repository()
    auth_manager = get_auth_manager()

    with repository.engine.connect() as connection:
        connection.execute(select(1))

    return {
        "status": "ok",
        "checks": {
            "database": "ok",
            "auth_secret": "ok" if bool(auth_manager.secret) else "missing",
            "environment": config.env,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

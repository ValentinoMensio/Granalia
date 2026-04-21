from __future__ import annotations

from fastapi import APIRouter

from ...dependencies import get_repository
from ...schemas import BootstrapOut, HealthOut


router = APIRouter(tags=["bootstrap"])


@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    return HealthOut(status="ok")


@router.get("/api/bootstrap", response_model=BootstrapOut)
def bootstrap() -> BootstrapOut:
    return BootstrapOut.model_validate(get_repository().bootstrap_payload())

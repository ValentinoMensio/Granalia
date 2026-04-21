from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .api.routes.auth import router as auth_router
from .api.routes.bootstrap import router as bootstrap_router
from .api.routes.customers import router as customers_router
from .api.routes.invoices import router as invoices_router
from .api.routes.lookups import router as lookups_router
from .api.routes.monitoring import router as monitoring_router
from .api.routes.price_lists import router as price_lists_router
from .core.config import load_config, validate_production_config
from .core.logging import configure_logging
from .dependencies import require_authenticated


def allowed_origins() -> list[str]:
    configured = os.getenv("GRANALIA_ALLOWED_ORIGINS")
    if configured:
        return [origin.strip() for origin in configured.split(",") if origin.strip()]
    return [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "https://granalia.localhost",
        "https://localhost",
    ]


config = load_config()
configure_logging(config.log_level, json_logs=config.log_json)
validate_production_config(config)
logger = logging.getLogger("granalia.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("starting granalia api")
    yield
    logger.info("stopping granalia api")


app = FastAPI(title="Granalia API", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    logging.getLogger("granalia.request").info(
        "%s %s -> %s in %sms",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    response.headers["X-Response-Time-Ms"] = str(duration_ms)
    return response

app.include_router(monitoring_router)
app.include_router(auth_router)
protected = [Depends(require_authenticated)]
app.include_router(bootstrap_router, dependencies=protected)
app.include_router(customers_router, dependencies=protected)
app.include_router(lookups_router, dependencies=protected)
app.include_router(invoices_router, dependencies=protected)
app.include_router(price_lists_router, dependencies=protected)

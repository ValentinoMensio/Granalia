from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AppConfig:
    env: str
    log_level: str
    log_json: bool
    postgres_url: str
    secure_cookies: bool
    session_secret: str | None

    @property
    def is_production(self) -> bool:
        return self.env.lower() == "production"


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_config() -> AppConfig:
    return AppConfig(
        env=os.getenv("GRANALIA_ENV", "development"),
        log_level=os.getenv("GRANALIA_LOG_LEVEL", "INFO").upper(),
        log_json=_env_flag("GRANALIA_LOG_JSON", True),
        postgres_url=os.getenv(
            "GRANALIA_POSTGRES_URL",
            "postgresql+psycopg://granalia:granalia@127.0.0.1:5432/granalia",
        ),
        secure_cookies=_env_flag("GRANALIA_SECURE_COOKIES", True),
        session_secret=os.getenv("GRANALIA_SESSION_SECRET"),
    )


def validate_production_config(config: AppConfig) -> None:
    if not config.is_production:
        return

    errors: list[str] = []
    if not config.session_secret or len(config.session_secret) < 32:
        errors.append("GRANALIA_SESSION_SECRET must be set with at least 32 chars")
    if not config.secure_cookies:
        errors.append("GRANALIA_SECURE_COOKIES must stay enabled in production")
    if "granalia:granalia@" in config.postgres_url:
        errors.append("GRANALIA_POSTGRES_URL cannot use default development credentials")

    if errors:
        raise RuntimeError("Invalid production configuration: " + "; ".join(errors))

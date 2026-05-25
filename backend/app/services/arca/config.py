from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ArcaConfig:
    environment: str
    cuit: str
    cert_path: str
    key_path: str
    key_passphrase: str
    wsfe_wsdl_homologation: str
    wsfe_wsdl_production: str
    default_point_of_sale: int | None
    token_cache_ttl_seconds: int

    @property
    def configured(self) -> bool:
        return bool(self.cuit and self.cert_path and self.key_path and self.default_point_of_sale)

    @property
    def wsfe_wsdl(self) -> str:
        return self.wsfe_wsdl_production if self.environment == "production" else self.wsfe_wsdl_homologation


def _env(name: str, fallback_name: str | None = None, default: str = "") -> str:
    return os.getenv(name) or (os.getenv(fallback_name) if fallback_name else None) or default


def _environment() -> str:
    value = _env("ARCA_ENV", "GRANALIA_ARCA_ENV", "homologation").strip().lower()
    return "production" if value in {"production", "produccion"} else "homologation"


def _optional_int(value: str) -> int | None:
    value = value.strip()
    return int(value) if value else None


def load_arca_config() -> ArcaConfig:
    return ArcaConfig(
        environment=_environment(),
        cuit=_env("ARCA_CUIT", "GRANALIA_ARCA_CUIT"),
        cert_path=_env("ARCA_WSAA_CERT_PATH", "GRANALIA_ARCA_CERT_PATH"),
        key_path=_env("ARCA_WSAA_KEY_PATH", "GRANALIA_ARCA_KEY_PATH"),
        key_passphrase=_env("ARCA_WSAA_PASSPHRASE", "GRANALIA_ARCA_KEY_PASSWORD"),
        wsfe_wsdl_homologation=_env("ARCA_WSFE_WSDL_HOMO", "GRANALIA_ARCA_WSFE_URL", "https://wswhomo.afip.gov.ar/wsfev1/service.asmx?WSDL"),
        wsfe_wsdl_production=_env("ARCA_WSFE_WSDL_PROD", default="https://servicios1.afip.gov.ar/wsfev1/service.asmx?WSDL"),
        default_point_of_sale=_optional_int(_env("ARCA_DEFAULT_POINT_OF_SALE", "GRANALIA_ARCA_POINT_OF_SALE")),
        token_cache_ttl_seconds=int(_env("ARCA_TOKEN_CACHE_TTL_SECONDS", default="36000")),
    )

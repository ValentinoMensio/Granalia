from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ArcaConfig:
    enabled: bool
    environment: str
    cuit: str
    point_of_sale: int | None
    service: str
    wsaa_url: str
    wsfe_url: str
    padron_url: str
    padron_service: str
    cert_path: str
    key_path: str
    key_password: str
    token_cache_path: str
    timeout_seconds: int
    dry_run: bool
    mark_authorized: bool
    receiver_iva_condition_id: int

    @property
    def is_configured(self) -> bool:
        return bool(self.enabled and self.cuit and self.point_of_sale and self.cert_path and self.key_path and self.service == "wsfev1")


def get_arca_config() -> ArcaConfig:
    point_of_sale = os.getenv("GRANALIA_ARCA_POINT_OF_SALE", "").strip()
    environment = os.getenv("GRANALIA_ARCA_ENV", "homologacion").strip() or "homologacion"
    if environment not in {"homologacion", "produccion"}:
        environment = "homologacion"
    service = "wsfev1"
    default_wsaa_url = "https://wsaahomo.afip.gov.ar/ws/services/LoginCms" if environment == "homologacion" else "https://wsaa.afip.gov.ar/ws/services/LoginCms"
    default_service_url = "https://wswhomo.afip.gov.ar/wsfev1/service.asmx" if environment == "homologacion" else "https://servicios1.afip.gov.ar/wsfev1/service.asmx"
    padron_service = os.getenv("GRANALIA_ARCA_PADRON_SERVICE", "ws_sr_padron_a4").strip().lower() or "ws_sr_padron_a4"
    if not padron_service.startswith("ws_sr_padron_"):
        padron_service = f"ws_sr_padron_{padron_service}"
    padron_scope = padron_service.rsplit("_", 1)[-1].upper()
    default_padron_host = "https://awshomo.afip.gov.ar" if environment == "homologacion" else "https://aws.afip.gov.ar"
    default_padron_url = f"{default_padron_host}/sr-padron/webservices/personaService{padron_scope}"
    timeout = os.getenv("GRANALIA_ARCA_TIMEOUT_SECONDS", "30").strip()
    mark_authorized = os.getenv("GRANALIA_ARCA_MARK_AUTHORIZED", "").strip().lower()
    receiver_iva_condition_id = os.getenv("GRANALIA_ARCA_RECEIVER_IVA_CONDITION_ID", "1").strip()
    return ArcaConfig(
        enabled=os.getenv("GRANALIA_ARCA_ENABLED", "false").strip().lower() == "true",
        environment=environment,
        cuit=os.getenv("GRANALIA_ARCA_CUIT", "").strip(),
        point_of_sale=int(point_of_sale) if point_of_sale.isdigit() else None,
        service=service,
        wsaa_url=os.getenv("GRANALIA_ARCA_WSAA_URL", default_wsaa_url).strip() or default_wsaa_url,
        wsfe_url=os.getenv("GRANALIA_ARCA_SERVICE_URL", os.getenv("GRANALIA_ARCA_WSFE_URL", default_service_url)).strip() or default_service_url,
        padron_url=os.getenv("GRANALIA_ARCA_PADRON_URL", default_padron_url).strip() or default_padron_url,
        padron_service=padron_service,
        cert_path=os.getenv("GRANALIA_ARCA_CERT_PATH", "").strip(),
        key_path=os.getenv("GRANALIA_ARCA_KEY_PATH", "").strip(),
        key_password=os.getenv("GRANALIA_ARCA_KEY_PASSWORD", "").strip(),
        token_cache_path=os.getenv("GRANALIA_ARCA_TOKEN_CACHE_PATH", str(Path("/tmp") / "granalia-arca-wsaa-token.json")).strip(),
        timeout_seconds=int(timeout) if timeout.isdigit() else 30,
        dry_run=os.getenv("GRANALIA_ARCA_DRY_RUN", "true").strip().lower() != "false",
        mark_authorized=(environment != "homologacion") if not mark_authorized else mark_authorized == "true",
        receiver_iva_condition_id=int(receiver_iva_condition_id) if receiver_iva_condition_id.isdigit() else 1,
    )

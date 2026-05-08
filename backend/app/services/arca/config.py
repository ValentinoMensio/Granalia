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
    padron_wsdl_url: str
    padron_url: str
    padron_service: str
    padron_namespace: str
    padron_operation: str
    padron_parser: str
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


def padron_service_defaults(environment: str, service_name: str) -> dict[str, str]:
    normalized = service_name.strip().lower() or "ws_sr_constancia_inscripcion"
    if normalized == "ws_sr_constancia_inscripcion":
        host = "https://awshomo.arca.gob.ar" if environment == "homologacion" else "https://aws.arca.gob.ar"
        wsdl_url = f"{host}/sr-padron/webservices/personaServiceA5?WSDL"
        return {
            "service": normalized,
            "wsdl_url": wsdl_url,
            "endpoint_url": wsdl_url.removesuffix("?WSDL"),
            "namespace": "http://a5.soap.ws.server.puc.sr/",
            "operation": "getPersona",
            "parser": "constancia_inscripcion",
        }

    if normalized.startswith("ws_sr_padron_"):
        scope = normalized.rsplit("_", 1)[-1].upper()
        host = "https://awshomo.afip.gov.ar" if environment == "homologacion" else "https://aws.afip.gov.ar"
        endpoint_url = f"{host}/sr-padron/webservices/personaService{scope}"
        return {
            "service": normalized,
            "wsdl_url": f"{endpoint_url}?WSDL",
            "endpoint_url": endpoint_url,
            "namespace": f"http://{scope.lower()}.soap.ws.server.puc.sr/",
            "operation": "getPersona",
            "parser": "padron",
        }

    raise ValueError(f"Servicio de padron ARCA no soportado: {service_name}")


def get_arca_config() -> ArcaConfig:
    point_of_sale = os.getenv("GRANALIA_ARCA_POINT_OF_SALE", "").strip()
    environment = os.getenv("GRANALIA_ARCA_ENV", "homologacion").strip() or "homologacion"
    if environment not in {"homologacion", "produccion"}:
        environment = "homologacion"
    service = "wsfev1"
    default_wsaa_url = "https://wsaahomo.afip.gov.ar/ws/services/LoginCms" if environment == "homologacion" else "https://wsaa.afip.gov.ar/ws/services/LoginCms"
    default_service_url = "https://wswhomo.afip.gov.ar/wsfev1/service.asmx" if environment == "homologacion" else "https://servicios1.afip.gov.ar/wsfev1/service.asmx"
    padron_defaults = padron_service_defaults(environment, os.getenv("GRANALIA_ARCA_PADRON_SERVICE", "ws_sr_constancia_inscripcion"))
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
        padron_wsdl_url=os.getenv("GRANALIA_ARCA_PADRON_WSDL_URL", padron_defaults["wsdl_url"]).strip() or padron_defaults["wsdl_url"],
        padron_url=os.getenv("GRANALIA_ARCA_PADRON_URL", padron_defaults["endpoint_url"]).strip() or padron_defaults["endpoint_url"],
        padron_service=padron_defaults["service"],
        padron_namespace=os.getenv("GRANALIA_ARCA_PADRON_NAMESPACE", padron_defaults["namespace"]).strip() or padron_defaults["namespace"],
        padron_operation=os.getenv("GRANALIA_ARCA_PADRON_OPERATION", padron_defaults["operation"]).strip() or padron_defaults["operation"],
        padron_parser=os.getenv("GRANALIA_ARCA_PADRON_PARSER", padron_defaults["parser"]).strip() or padron_defaults["parser"],
        cert_path=os.getenv("GRANALIA_ARCA_CERT_PATH", "").strip(),
        key_path=os.getenv("GRANALIA_ARCA_KEY_PATH", "").strip(),
        key_password=os.getenv("GRANALIA_ARCA_KEY_PASSWORD", "").strip(),
        token_cache_path=os.getenv("GRANALIA_ARCA_TOKEN_CACHE_PATH", str(Path("/tmp") / "granalia-arca-wsaa-token.json")).strip(),
        timeout_seconds=int(timeout) if timeout.isdigit() else 30,
        dry_run=os.getenv("GRANALIA_ARCA_DRY_RUN", "true").strip().lower() != "false",
        mark_authorized=(environment != "homologacion") if not mark_authorized else mark_authorized == "true",
        receiver_iva_condition_id=int(receiver_iva_condition_id) if receiver_iva_condition_id.isdigit() else 1,
    )

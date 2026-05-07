from __future__ import annotations

import socket
import ssl
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import logging
from dataclasses import replace
from pathlib import Path
from xml.sax.saxutils import escape

from .config import ArcaConfig, get_arca_config
from .models import ArcaAuthTicket
from .wsaa import WsaaError, get_auth_ticket


logger = logging.getLogger(__name__)


class ArcaPadronError(RuntimeError):
    pass


def digits_only(value: object) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def first_child(root: ET.Element | None, name: str) -> ET.Element | None:
    if root is None:
        return None
    for element in root.iter():
        if local_name(element.tag) == name:
            return element
    return None


def first_text(root: ET.Element | None, name: str) -> str:
    element = first_child(root, name)
    return element.text.strip() if element is not None and element.text else ""


def first_text_any(root: ET.Element | None, names: tuple[str, ...]) -> str:
    for name in names:
        value = first_text(root, name)
        if value:
            return value
    return ""


def all_texts(root: ET.Element | None, name: str) -> list[str]:
    if root is None:
        return []
    return [element.text.strip() for element in root.iter() if local_name(element.tag) == name and element.text]


def descendant_texts(root: ET.Element | None) -> list[str]:
    if root is None:
        return []
    return [element.text.strip() for element in root.iter() if element.text and element.text.strip()]


def response_error(root: ET.Element) -> str:
    for name in ("faultstring", "descripcionError", "error"):
        value = first_text(root, name)
        if value:
            return value
    error_constancia = first_child(root, "errorConstancia")
    texts = descendant_texts(error_constancia)
    return "; ".join(texts)


def padron_config(config: ArcaConfig) -> ArcaConfig:
    cache_path = Path(config.token_cache_path)
    service = config.padron_service or "ws_sr_padron_a5"
    return replace(
        config,
        service=service,
        token_cache_path=str(cache_path.with_name(f"{cache_path.stem}-{service}{cache_path.suffix}")),
    )


def padron_scope(config: ArcaConfig) -> str:
    return (config.padron_service or config.service or "ws_sr_padron_a5").rsplit("_", 1)[-1].lower()


def padron_namespace(config: ArcaConfig) -> str:
    return f"http://{padron_scope(config)}.soap.ws.server.puc.sr/"


def auth_xml(config: ArcaConfig, ticket: ArcaAuthTicket, cuit: str) -> str:
    return f"""<token>{escape(ticket.token)}</token>
<sign>{escape(ticket.sign)}</sign>
<cuitRepresentada>{escape(config.cuit)}</cuitRepresentada>
<idPersona>{escape(cuit)}</idPersona>"""


def soap_envelope(config: ArcaConfig, body: str) -> str:
    namespace = padron_namespace(config)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:padron="{namespace}">
  <soapenv:Header/>
  <soapenv:Body>
    <padron:getPersona>{body}</padron:getPersona>
  </soapenv:Body>
</soapenv:Envelope>"""


def request_persona(config: ArcaConfig, ticket: ArcaAuthTicket, cuit: str) -> ET.Element:
    namespace = padron_namespace(config)
    request = urllib.request.Request(
        config.padron_url,
        data=soap_envelope(config, auth_xml(config, ticket, cuit)).encode("utf-8"),
        headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": f"{namespace}getPersona"},
        method="POST",
    )
    context = ssl.create_default_context()
    context.set_ciphers("DEFAULT:@SECLEVEL=1")
    try:
        with urllib.request.urlopen(request, timeout=config.timeout_seconds, context=context) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        try:
            root = ET.fromstring(body)
            fault = first_text(root, "faultstring") or first_text(root, "descripcionError") or first_text(root, "errorConstancia")
        except ET.ParseError:
            fault = body.strip()
        raise ArcaPadronError(f"HTTP {error.code}: {fault or error.reason}") from error
    except (socket.timeout, TimeoutError, urllib.error.URLError) as error:
        raise ArcaPadronError(f"No se pudo consultar padron ARCA: {error}") from error
    root = ET.fromstring(body)
    error = response_error(root)
    if error:
        raise ArcaPadronError(error)
    return root


def iva_condition(root: ET.Element) -> str:
    if first_child(root, "datosGenerales") is None and first_child(root, "datosMonotributo") is None and first_child(root, "datosRegimenGeneral") is None:
        return ""
    if first_child(root, "datosMonotributo") is not None:
        return "Responsable Monotributo"
    tax_ids = set(all_texts(root, "idImpuesto"))
    tax_descriptions = " ".join(all_texts(root, "descripcionImpuesto")).lower()
    if "30" in tax_ids or "valor agregado" in tax_descriptions or " iva" in f" {tax_descriptions}":
        return "IVA Responsable Inscripto"
    return "IVA Sujeto Exento"


def fiscal_name(root: ET.Element) -> str:
    razon_social = first_text_any(root, ("razonSocial", "denominacion", "nombreCompleto"))
    if razon_social:
        return razon_social
    parts = [first_text(root, "apellido"), first_text(root, "nombre")]
    return " ".join(part for part in parts if part).strip()


def fiscal_address(root: ET.Element) -> str:
    domicilio = first_child(root, "domicilioFiscal") or first_child(root, "domicilio")
    direccion = first_text_any(domicilio, ("direccion", "calle"))
    numero = first_text(domicilio, "numero")
    if numero and numero not in direccion:
        direccion = f"{direccion} {numero}".strip()
    parts = [
        direccion,
        first_text(domicilio, "localidad"),
        first_text_any(domicilio, ("descripcionProvincia", "provincia")),
    ]
    return ", ".join(part for part in parts if part).strip()


def response_field_names(root: ET.Element) -> list[str]:
    names = sorted({local_name(element.tag) for element in root.iter()})
    return names[:80]


def lookup_taxpayer_data(cuit: object, config: ArcaConfig | None = None) -> dict[str, object]:
    cuit_digits = digits_only(cuit)
    if len(cuit_digits) != 11:
        return {"ok": False, "cuit": cuit_digits, "data": None, "error": "CUIT invalido"}
    base_config = config or get_arca_config()
    result: dict[str, object] = {
        "ok": False,
        "cuit": cuit_digits,
        "environment": base_config.environment,
        "service": base_config.padron_service,
        "ta_service": base_config.padron_service,
        "wsaa_url": base_config.wsaa_url,
        "url": base_config.padron_url,
        "configured": bool(base_config.enabled and base_config.cuit and base_config.cert_path and base_config.key_path),
        "data": None,
        "error": None,
    }
    if not base_config.enabled or not base_config.cuit or not base_config.cert_path or not base_config.key_path:
        result["error"] = "ARCA padron no configurado"
        return result
    config = padron_config(base_config)
    try:
        ticket = get_auth_ticket(config)
        root = request_persona(config, ticket, cuit_digits)
    except (ArcaPadronError, WsaaError, ET.ParseError, ValueError) as error:
        logger.warning("No se pudieron obtener datos fiscales ARCA para CUIT %s: %s", cuit_digits, error)
        result["error"] = str(error)
        return result
    data = {
        "cuit": cuit_digits,
        "business_name": fiscal_name(root),
        "address": fiscal_address(root),
        "iva_condition": iva_condition(root),
    }
    result["data"] = {key: value for key, value in data.items() if value}
    result["fields"] = response_field_names(root)
    result["ok"] = bool(data["business_name"] or data["address"])
    if not result["ok"]:
        result["error"] = "ARCA no devolvio razon social ni domicilio para ese CUIT"
    return result


def get_taxpayer_data(cuit: object, config: ArcaConfig | None = None) -> dict[str, str] | None:
    result = lookup_taxpayer_data(cuit, config)
    data = result.get("data")
    return data if isinstance(data, dict) else None

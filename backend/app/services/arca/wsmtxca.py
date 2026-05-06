from __future__ import annotations

import socket
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime
from decimal import Decimal
from xml.sax.saxutils import escape

from .config import ArcaConfig
from .models import ArcaAuthTicket, ArcaAuthorizationResult, ArcaInvoiceRequest


NS = "http://impl.service.wsmtxca.afip.gov.ar/service/"
SOAP_ACTION_BASE = "http://impl.service.wsmtxca.afip.gov.ar/service"


class WsmtxcaError(RuntimeError):
    pass


class WsmtxcaTechnicalError(WsmtxcaError):
    pass


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def first_child(root: ET.Element, name: str) -> ET.Element | None:
    for element in root.iter():
        if local_name(element.tag) == name:
            return element
    return None


def direct_text(root: ET.Element, name: str) -> str:
    for child in list(root):
        if local_name(child.tag) == name:
            return child.text or ""
    return ""


def first_text(root: ET.Element, name: str) -> str:
    element = first_child(root, name)
    return element.text if element is not None and element.text is not None else ""


def decimal_text(value: Decimal) -> str:
    return f"{value:.2f}"


def quantity_text(value: Decimal) -> str:
    return f"{value:.6f}"


def parse_date(value: str) -> date | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(value[:10], fmt).date()
        except ValueError:
            continue
    return None


def auth_xml(config: ArcaConfig, ticket: ArcaAuthTicket) -> str:
    return f"""<authRequest>
  <token>{escape(ticket.token)}</token>
  <sign>{escape(ticket.sign)}</sign>
  <cuitRepresentada>{escape(config.cuit)}</cuitRepresentada>
</authRequest>"""


def soap_envelope(request_element: str, body: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ar="{NS}">
  <soapenv:Header/>
  <soapenv:Body>
    <ar:{request_element}>{body}</ar:{request_element}>
  </soapenv:Body>
</soapenv:Envelope>"""


def parse_code_descriptions(root: ET.Element, container_name: str) -> list[dict[str, object]]:
    container = first_child(root, container_name)
    if container is None:
        return []
    items: list[dict[str, object]] = []
    for item in container.iter():
        if local_name(item.tag) != "codigoDescripcion":
            continue
        items.append({"Code": direct_text(item, "codigo"), "Msg": direct_text(item, "descripcion")})
    return items


def parse_items(root: ET.Element) -> list[dict[str, str]]:
    container = first_child(root, "arrayItems")
    if container is None:
        return []
    items: list[dict[str, str]] = []
    for item in container.iter():
        if local_name(item.tag) != "item":
            continue
        items.append(
            {
                "codigo": direct_text(item, "codigo"),
                "descripcion": direct_text(item, "descripcion"),
                "cantidad": direct_text(item, "cantidad"),
                "codigoUnidadMedida": direct_text(item, "codigoUnidadMedida"),
                "precioUnitario": direct_text(item, "precioUnitario"),
                "importeBonificacion": direct_text(item, "importeBonificacion"),
                "codigoCondicionIVA": direct_text(item, "codigoCondicionIVA"),
                "importeIVA": direct_text(item, "importeIVA"),
                "importeItem": direct_text(item, "importeItem"),
            }
        )
    return items


def request_operation(config: ArcaConfig, operation: str, request_element: str, body: str) -> ET.Element:
    request = urllib.request.Request(
        config.wsfe_url,
        data=soap_envelope(request_element, body).encode("utf-8"),
        headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": f"{SOAP_ACTION_BASE}/{operation}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
            response_body = response.read().decode("utf-8")
    except (socket.timeout, TimeoutError, urllib.error.URLError) as error:
        raise WsmtxcaTechnicalError(f"Error tecnico WSMTXCA: {error}") from error
    root = ET.fromstring(response_body)
    fault = first_text(root, "faultstring") or first_text(root, "exception")
    if fault:
        raise WsmtxcaError(fault)
    errors = parse_code_descriptions(root, "arrayErrores")
    if errors:
        message = "; ".join(str(item.get("Msg") or item.get("Code")) for item in errors)
        raise WsmtxcaError(message)
    return root


def iva_condition_code(arca_iva_id: int) -> int:
    return arca_iva_id


class WsmtxcaClient:
    def __init__(self, config: ArcaConfig, ticket: ArcaAuthTicket) -> None:
        self.config = config
        self.ticket = ticket

    def get_points_of_sale(self) -> list[int]:
        root = request_operation(self.config, "consultarPuntosVentaCAE", "consultarPuntosVentaCAERequest", auth_xml(self.config, self.ticket))
        points: list[int] = []
        for item in root.iter():
            if local_name(item.tag) != "puntoVenta":
                continue
            number = direct_text(item, "numeroPuntoVenta")
            blocked = direct_text(item, "bloqueado")
            if number.isdigit() and blocked != "S":
                points.append(int(number))
        return points

    def get_last_authorized(self, point_of_sale: int, cbte_tipo: int) -> int:
        body = f"""{auth_xml(self.config, self.ticket)}
<consultaUltimoComprobanteAutorizadoRequest>
  <codigoTipoComprobante>{cbte_tipo}</codigoTipoComprobante>
  <numeroPuntoVenta>{point_of_sale}</numeroPuntoVenta>
</consultaUltimoComprobanteAutorizadoRequest>"""
        root = request_operation(self.config, "consultarUltimoComprobanteAutorizado", "consultarUltimoComprobanteAutorizadoRequest", body)
        value = first_text(root, "numeroComprobante")
        return int(value) if value.isdigit() else 0

    def get_invoice_by_number(self, point_of_sale: int, cbte_tipo: int, cbte_nro: int) -> ArcaAuthorizationResult | None:
        body = f"""{auth_xml(self.config, self.ticket)}
<consultaComprobanteRequest>
  <codigoTipoComprobante>{cbte_tipo}</codigoTipoComprobante>
  <numeroPuntoVenta>{point_of_sale}</numeroPuntoVenta>
  <numeroComprobante>{cbte_nro}</numeroComprobante>
</consultaComprobanteRequest>"""
        root = request_operation(self.config, "consultarComprobante", "consultarComprobanteRequest", body)
        comprobante = first_child(root, "comprobante")
        if comprobante is None:
            return None
        cae = direct_text(comprobante, "codigoAutorizacion")
        return ArcaAuthorizationResult(
            result="A" if cae else "R",
            invoice_number=cbte_nro,
            cae=cae or None,
            cae_expires_at=parse_date(direct_text(comprobante, "fechaVencimiento")),
            observations=parse_code_descriptions(root, "arrayObservaciones"),
            raw={"numeroComprobante": cbte_nro, "codigoAutorizacion": cae, "items": parse_items(comprobante)},
        )

    def request_cae(self, request: ArcaInvoiceRequest, cbte_nro: int) -> ArcaAuthorizationResult:
        cbte_date = request.cbte_date.isoformat()
        items_xml = "".join(
            f"""<item>
  <codigo>{escape(item.code)}</codigo>
  <descripcion>{escape(item.description)}</descripcion>
  <cantidad>{quantity_text(item.quantity)}</cantidad>
  <codigoUnidadMedida>{item.unit_code}</codigoUnidadMedida>
  <precioUnitario>{decimal_text(item.unit_price)}</precioUnitario>
  <importeBonificacion>{decimal_text(item.discount_amount)}</importeBonificacion>
  <codigoCondicionIVA>{iva_condition_code(item.iva_id)}</codigoCondicionIVA>
  <importeIVA>{decimal_text(item.iva_amount)}</importeIVA>
  <importeItem>{decimal_text(item.item_total)}</importeItem>
</item>"""
            for item in request.items
        )
        subtotals_xml = "".join(
            f"""<subtotalIVA>
  <codigo>{item.Id}</codigo>
  <importe>{decimal_text(item.Importe)}</importe>
</subtotalIVA>"""
            for item in request.iva
        )
        body = f"""{auth_xml(self.config, self.ticket)}
<comprobanteCAERequest>
  <codigoTipoComprobante>{request.cbte_tipo}</codigoTipoComprobante>
  <numeroPuntoVenta>{request.point_of_sale}</numeroPuntoVenta>
  <numeroComprobante>{cbte_nro}</numeroComprobante>
  <fechaEmision>{cbte_date}</fechaEmision>
  <codigoTipoDocumento>{request.doc_tipo}</codigoTipoDocumento>
  <numeroDocumento>{escape(request.doc_nro)}</numeroDocumento>
  <condicionIVAReceptor>1</condicionIVAReceptor>
  <importeGravado>{decimal_text(request.imp_neto)}</importeGravado>
  <importeNoGravado>0.00</importeNoGravado>
  <importeExento>0.00</importeExento>
  <importeSubtotal>{decimal_text(request.imp_neto)}</importeSubtotal>
  <importeOtrosTributos>0.00</importeOtrosTributos>
  <importeTotal>{decimal_text(request.imp_total)}</importeTotal>
  <codigoMoneda>PES</codigoMoneda>
  <cotizacionMoneda>1.000000</cotizacionMoneda>
  <codigoConcepto>{request.concepto}</codigoConcepto>
  <arrayItems>{items_xml}</arrayItems>
  <arraySubtotalesIVA>{subtotals_xml}</arraySubtotalesIVA>
</comprobanteCAERequest>"""
        root = request_operation(self.config, "autorizarComprobante", "autorizarComprobanteRequest", body)
        result = first_text(root, "resultado")
        response = first_child(root, "comprobanteResponse")
        cae = direct_text(response, "CAE") if response is not None else ""
        invoice_number = direct_text(response, "numeroComprobante") if response is not None else str(cbte_nro)
        return ArcaAuthorizationResult(
            result=result,
            invoice_number=int(invoice_number) if invoice_number.isdigit() else cbte_nro,
            cae=cae or None,
            cae_expires_at=parse_date(direct_text(response, "fechaVencimientoCAE") if response is not None else ""),
            observations=parse_code_descriptions(root, "arrayObservaciones"),
            raw={"resultado": result, "numeroComprobante": invoice_number, "observaciones": parse_code_descriptions(root, "arrayObservaciones")},
        )

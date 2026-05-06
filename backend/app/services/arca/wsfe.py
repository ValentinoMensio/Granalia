from __future__ import annotations

import socket
import ssl
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime
from decimal import Decimal
from xml.sax.saxutils import escape

from .config import ArcaConfig
from .models import ArcaAuthTicket, ArcaAuthorizationResult, ArcaInvoiceRequest


NS = "http://ar.gov.afip.dif.FEV1/"


class WsfeError(RuntimeError):
    pass


class WsfeTechnicalError(WsfeError):
    pass


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def first_child(root: ET.Element, name: str) -> ET.Element | None:
    for element in root.iter():
        if local_name(element.tag) == name:
            return element
    return None


def first_text(root: ET.Element, name: str) -> str:
    element = first_child(root, name)
    return element.text if element is not None and element.text is not None else ""


def decimal_text(value: Decimal) -> str:
    return f"{value:.2f}"


def parse_yyyymmdd(value: str) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError:
        return None


def auth_xml(config: ArcaConfig, ticket: ArcaAuthTicket) -> str:
    return f"""<ar:Auth>
  <ar:Token>{escape(ticket.token)}</ar:Token>
  <ar:Sign>{escape(ticket.sign)}</ar:Sign>
  <ar:Cuit>{escape(config.cuit)}</ar:Cuit>
</ar:Auth>"""


def soap_envelope(operation: str, body: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ar="{NS}">
  <soapenv:Header/>
  <soapenv:Body>
    <ar:{operation}>{body}</ar:{operation}>
  </soapenv:Body>
</soapenv:Envelope>"""


def request_operation(config: ArcaConfig, operation: str, body: str) -> ET.Element:
    request = urllib.request.Request(
        config.wsfe_url,
        data=soap_envelope(operation, body).encode("utf-8"),
        headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": f"{NS}{operation}"},
        method="POST",
    )
    context = ssl.create_default_context()
    context.set_ciphers("DEFAULT:@SECLEVEL=1")
    try:
        with urllib.request.urlopen(request, timeout=config.timeout_seconds, context=context) as response:
            response_body = response.read().decode("utf-8")
    except (socket.timeout, TimeoutError, urllib.error.URLError) as error:
        raise WsfeTechnicalError(f"Error tecnico WSFE: {error}") from error
    root = ET.fromstring(response_body)
    fault = first_text(root, "faultstring")
    if fault:
        raise WsfeError(fault)
    errors = parse_errors(root)
    if errors:
        message = "; ".join(str(item.get("Msg") or item.get("Code")) for item in errors)
        raise WsfeError(message)
    return root


def parse_errors(root: ET.Element) -> list[dict[str, object]]:
    errors: list[dict[str, object]] = []
    for err in root.iter():
        if local_name(err.tag) != "Err":
            continue
        errors.append({"Code": first_text(err, "Code"), "Msg": first_text(err, "Msg")})
    return errors


def parse_observations(root: ET.Element) -> list[dict[str, object]]:
    observations: list[dict[str, object]] = []
    for obs in root.iter():
        if local_name(obs.tag) != "Obs":
            continue
        observations.append({"Code": first_text(obs, "Code"), "Msg": first_text(obs, "Msg")})
    return observations


class WsfeClient:
    def __init__(self, config: ArcaConfig, ticket: ArcaAuthTicket) -> None:
        self.config = config
        self.ticket = ticket

    def get_points_of_sale(self) -> list[int]:
        root = request_operation(self.config, "FEParamGetPtosVenta", auth_xml(self.config, self.ticket))
        points: list[int] = []
        for item in root.iter():
            if local_name(item.tag) != "PtoVenta":
                continue
            nro = first_text(item, "Nro")
            if nro.isdigit():
                points.append(int(nro))
        return points

    def get_last_authorized(self, point_of_sale: int, cbte_tipo: int) -> int:
        body = f"""{auth_xml(self.config, self.ticket)}
<ar:PtoVta>{point_of_sale}</ar:PtoVta>
<ar:CbteTipo>{cbte_tipo}</ar:CbteTipo>"""
        root = request_operation(self.config, "FECompUltimoAutorizado", body)
        value = first_text(root, "CbteNro")
        return int(value) if value.isdigit() else 0

    def get_invoice_by_number(self, point_of_sale: int, cbte_tipo: int, cbte_nro: int) -> ArcaAuthorizationResult | None:
        body = f"""{auth_xml(self.config, self.ticket)}
<ar:FeCompConsReq>
  <ar:CbteTipo>{cbte_tipo}</ar:CbteTipo>
  <ar:CbteNro>{cbte_nro}</ar:CbteNro>
  <ar:PtoVta>{point_of_sale}</ar:PtoVta>
</ar:FeCompConsReq>"""
        root = request_operation(self.config, "FECompConsultar", body)
        result = first_text(root, "Resultado")
        if not result:
            return None
        return ArcaAuthorizationResult(
            result=result,
            invoice_number=cbte_nro,
            cae=first_text(root, "CodAutorizacion") or None,
            cae_expires_at=parse_yyyymmdd(first_text(root, "FchVto")),
            observations=parse_observations(root),
            raw={"Resultado": result, "CbteNro": cbte_nro},
        )

    def request_cae(self, request: ArcaInvoiceRequest, cbte_nro: int) -> ArcaAuthorizationResult:
        today = datetime.now().strftime("%Y%m%d")
        iva_xml = "".join(
            f"""<ar:AlicIva>
  <ar:Id>{item.Id}</ar:Id>
  <ar:BaseImp>{decimal_text(item.BaseImp)}</ar:BaseImp>
  <ar:Importe>{decimal_text(item.Importe)}</ar:Importe>
</ar:AlicIva>"""
            for item in request.iva
        )
        body = f"""{auth_xml(self.config, self.ticket)}
<ar:FeCAEReq>
  <ar:FeCabReq>
    <ar:CantReg>1</ar:CantReg>
    <ar:PtoVta>{request.point_of_sale}</ar:PtoVta>
    <ar:CbteTipo>{request.cbte_tipo}</ar:CbteTipo>
  </ar:FeCabReq>
  <ar:FeDetReq>
    <ar:FECAEDetRequest>
      <ar:Concepto>{request.concepto}</ar:Concepto>
      <ar:DocTipo>{request.doc_tipo}</ar:DocTipo>
      <ar:DocNro>{escape(request.doc_nro)}</ar:DocNro>
      <ar:CbteDesde>{cbte_nro}</ar:CbteDesde>
      <ar:CbteHasta>{cbte_nro}</ar:CbteHasta>
      <ar:CbteFch>{today}</ar:CbteFch>
      <ar:ImpTotal>{decimal_text(request.imp_total)}</ar:ImpTotal>
      <ar:ImpTotConc>0.00</ar:ImpTotConc>
      <ar:ImpNeto>{decimal_text(request.imp_neto)}</ar:ImpNeto>
      <ar:ImpOpEx>0.00</ar:ImpOpEx>
      <ar:ImpTrib>0.00</ar:ImpTrib>
      <ar:ImpIVA>{decimal_text(request.imp_iva)}</ar:ImpIVA>
      <ar:MonId>PES</ar:MonId>
      <ar:MonCotiz>1.00</ar:MonCotiz>
      <ar:CondicionIVAReceptorId>{request.condicion_iva_receptor_id}</ar:CondicionIVAReceptorId>
      <ar:Iva>{iva_xml}</ar:Iva>
    </ar:FECAEDetRequest>
  </ar:FeDetReq>
</ar:FeCAEReq>"""
        root = request_operation(self.config, "FECAESolicitar", body)
        detail = first_child(root, "FECAEDetResponse") or root
        result = first_text(detail, "Resultado") or first_text(root, "Resultado")
        invoice_number = first_text(detail, "CbteDesde") or str(cbte_nro)
        return ArcaAuthorizationResult(
            result=result,
            invoice_number=int(invoice_number) if invoice_number.isdigit() else cbte_nro,
            cae=first_text(detail, "CAE") or None,
            cae_expires_at=parse_yyyymmdd(first_text(detail, "CAEFchVto")),
            observations=parse_observations(detail),
            raw={"Resultado": result, "CbteDesde": invoice_number, "Observaciones": parse_observations(detail)},
        )

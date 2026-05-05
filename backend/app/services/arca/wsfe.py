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
    return f"""<Auth>
  <Token>{escape(ticket.token)}</Token>
  <Sign>{escape(ticket.sign)}</Sign>
  <Cuit>{escape(config.cuit)}</Cuit>
</Auth>"""


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
    try:
        with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
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
<PtoVta>{point_of_sale}</PtoVta>
<CbteTipo>{cbte_tipo}</CbteTipo>"""
        root = request_operation(self.config, "FECompUltimoAutorizado", body)
        value = first_text(root, "CbteNro")
        return int(value) if value.isdigit() else 0

    def get_invoice_by_number(self, point_of_sale: int, cbte_tipo: int, cbte_nro: int) -> ArcaAuthorizationResult | None:
        body = f"""{auth_xml(self.config, self.ticket)}
<FeCompConsReq>
  <CbteTipo>{cbte_tipo}</CbteTipo>
  <CbteNro>{cbte_nro}</CbteNro>
  <PtoVta>{point_of_sale}</PtoVta>
</FeCompConsReq>"""
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
            f"""<AlicIva>
  <Id>{item.Id}</Id>
  <BaseImp>{decimal_text(item.BaseImp)}</BaseImp>
  <Importe>{decimal_text(item.Importe)}</Importe>
</AlicIva>"""
            for item in request.iva
        )
        body = f"""{auth_xml(self.config, self.ticket)}
<FeCAEReq>
  <FeCabReq>
    <CantReg>1</CantReg>
    <PtoVta>{request.point_of_sale}</PtoVta>
    <CbteTipo>{request.cbte_tipo}</CbteTipo>
  </FeCabReq>
  <FeDetReq>
    <FECAEDetRequest>
      <Concepto>{request.concepto}</Concepto>
      <DocTipo>{request.doc_tipo}</DocTipo>
      <DocNro>{escape(request.doc_nro)}</DocNro>
      <CbteDesde>{cbte_nro}</CbteDesde>
      <CbteHasta>{cbte_nro}</CbteHasta>
      <CbteFch>{today}</CbteFch>
      <ImpTotal>{decimal_text(request.imp_total)}</ImpTotal>
      <ImpTotConc>0.00</ImpTotConc>
      <ImpNeto>{decimal_text(request.imp_neto)}</ImpNeto>
      <ImpOpEx>0.00</ImpOpEx>
      <ImpTrib>0.00</ImpTrib>
      <ImpIVA>{decimal_text(request.imp_iva)}</ImpIVA>
      <MonId>PES</MonId>
      <MonCotiz>1.00</MonCotiz>
      <Iva>{iva_xml}</Iva>
    </FECAEDetRequest>
  </FeDetReq>
</FeCAEReq>"""
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

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from .client import ArcaClient, ArcaDisabledError, ArcaNotConfiguredError, ArcaRejectedError, ArcaTechnicalError
from .config import get_arca_config
from .models import ArcaInvoiceItem, ArcaInvoiceRequest, ArcaIvaItem


class ArcaAuthorizationConflict(RuntimeError):
    pass


def money_decimal(value: object) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def digits_only(value: object) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def arca_iva_id_for_rate(value: object) -> int:
    return 4 if Decimal(str(value)) == Decimal("0.105") else 5


def arca_error_status(error: Exception) -> str:
    if isinstance(error, (ArcaDisabledError, ArcaNotConfiguredError, ArcaTechnicalError)):
        return "error"
    return "rejected"


def build_arca_invoice_items(invoice: dict) -> list[ArcaInvoiceItem]:
    items: list[ArcaInvoiceItem] = []
    for item in invoice.get("items", []):
        iva_rate = item.get("iva_rate") if item.get("iva_rate") is not None else item.get("product_iva_rate")
        if iva_rate is None:
            raise ValueError(f"Falta IVA fiscal para {item.get('label')}")
        quantity = Decimal(str(item.get("quantity") or 0))
        if quantity <= 0:
            continue
        unit_price = money_decimal(item.get("unit_price"))
        gross = money_decimal(item.get("gross"))
        net_amount = money_decimal(item.get("effective_total") if item.get("effective_total") is not None else item.get("net_amount") if item.get("net_amount") is not None else item.get("total"))
        iva_amount = money_decimal(item.get("iva_amount") if item.get("iva_amount") is not None else net_amount * Decimal(str(iva_rate)))
        fiscal_total = money_decimal(item.get("fiscal_total") if item.get("fiscal_total") is not None else net_amount + iva_amount)
        discount_amount = money_decimal(item.get("effective_discount") if item.get("effective_discount") is not None else max(Decimal("0"), gross - net_amount))
        description = " ".join(str(part or "").strip() for part in (item.get("product_name"), item.get("offering_label")) if str(part or "").strip())
        items.append(
            ArcaInvoiceItem(
                code=str(item.get("product_id") or item.get("id") or item.get("line_number") or ""),
                description=description or str(item.get("label") or "Producto"),
                quantity=quantity.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP),
                unit_code=62,
                unit_price=unit_price,
                discount_amount=discount_amount,
                iva_id=arca_iva_id_for_rate(iva_rate),
                iva_amount=iva_amount,
                item_total=fiscal_total,
            )
        )
    if not items:
        raise ValueError("La factura no tiene items fiscales para ARCA")
    return items


def build_arca_invoice_request(invoice: dict, tax_breakdown: list[dict], *, point_of_sale: int, receiver_iva_condition_id: int) -> ArcaInvoiceRequest:
    doc_nro = digits_only(invoice.get("customer_cuit"))
    if len(doc_nro) != 11:
        raise ValueError("Cliente con CUIT invalido")
    arca_items = build_arca_invoice_items(invoice)
    if tax_breakdown:
        iva_items = [ArcaIvaItem(Id=int(item["arca_iva_id"]), BaseImp=money_decimal(item["base_amount"]), Importe=money_decimal(item["iva_amount"])) for item in tax_breakdown]
    else:
        iva_breakdown: dict[int, dict[str, Decimal]] = {}
        for item in arca_items:
            current = iva_breakdown.setdefault(item.iva_id, {"base": Decimal("0"), "iva": Decimal("0")})
            current["base"] += item.item_total - item.iva_amount
            current["iva"] += item.iva_amount
        iva_items = [ArcaIvaItem(Id=iva_id, BaseImp=money_decimal(values["base"]), Importe=money_decimal(values["iva"])) for iva_id, values in sorted(iva_breakdown.items())]
    imp_neto = money_decimal(sum(item.BaseImp for item in iva_items))
    imp_iva = money_decimal(sum(item.Importe for item in iva_items))
    try:
        cbte_date = datetime.strptime(str(invoice.get("order_date")), "%Y-%m-%d").date()
    except ValueError:
        cbte_date = date.today()
    return ArcaInvoiceRequest(
        invoice_id=int(invoice["id"]),
        cbte_date=cbte_date,
        point_of_sale=point_of_sale,
        cbte_tipo=1,
        concepto=1,
        doc_tipo=80,
        doc_nro=doc_nro,
        condicion_iva_receptor_id=receiver_iva_condition_id,
        imp_neto=imp_neto,
        imp_iva=imp_iva,
        imp_total=money_decimal(imp_neto + imp_iva),
        iva=iva_items,
        items=arca_items,
    )


def sanitized_wsfe_payload(request: ArcaInvoiceRequest) -> dict[str, object]:
    return {
        "invoice_id": request.invoice_id,
        "CbteFch": request.cbte_date.strftime("%Y%m%d"),
        "CbteTipo": request.cbte_tipo,
        "Concepto": request.concepto,
        "DocTipo": request.doc_tipo,
        "DocNro": request.doc_nro,
        "CondicionIVAReceptorId": request.condicion_iva_receptor_id,
        "PtoVta": request.point_of_sale,
        "ImpNeto": str(request.imp_neto),
        "ImpIVA": str(request.imp_iva),
        "ImpTotal": str(request.imp_total),
        "Iva": [{"Id": item.Id, "BaseImp": str(item.BaseImp), "Importe": str(item.Importe)} for item in request.iva],
    }


def sanitized_arca_response(response: dict[str, object]) -> dict[str, object]:
    return {key: (value.isoformat() if hasattr(value, "isoformat") else value) for key, value in response.items()}


def authorize_invoice_in_arca(repository, invoice_id: int) -> dict[str, object]:
    invoice = repository.get_invoice_detail(invoice_id)
    if not invoice:
        raise ValueError("Factura no encontrada")
    if invoice.get("arca_cae") and invoice.get("arca_invoice_number"):
        return {"invoice_id": invoice_id, "fiscal_status": "authorized", "arca_request_id": invoice.get("arca_request_id"), "message": "La factura ya tiene CAE y numero ARCA."}
    fiscal_status = str(invoice.get("fiscal_status") or "")
    if fiscal_status == "authorizing":
        raise ArcaAuthorizationConflict("La factura fiscal ya se esta autorizando")
    if fiscal_status == "authorized":
        raise ValueError("La factura fiscal ya esta autorizada")
    if fiscal_status not in {"draft", "rejected", "error"}:
        raise ValueError("Solo se pueden autorizar facturas fiscales")
    if str(invoice.get("split_kind") or "") != "fiscal" and not bool(invoice.get("declared")):
        raise ValueError("Solo se pueden autorizar facturas fiscales")
    if not repository.reserve_invoice_arca_authorization(invoice_id):
        current_invoice = repository.get_invoice_detail(invoice_id)
        if current_invoice and current_invoice.get("arca_cae") and current_invoice.get("arca_invoice_number"):
            return {"invoice_id": invoice_id, "fiscal_status": "authorized", "arca_request_id": current_invoice.get("arca_request_id"), "message": "La factura ya tiene CAE y numero ARCA."}
        raise ArcaAuthorizationConflict("La factura fiscal ya se esta autorizando")

    invoice = repository.get_invoice_detail(invoice_id) or invoice
    config = get_arca_config()
    try:
        if not config.is_configured:
            arca_request = ArcaInvoiceRequest(
                invoice_id=invoice_id,
                cbte_date=date.today(),
                point_of_sale=config.point_of_sale or 0,
                cbte_tipo=1,
                concepto=1,
                doc_tipo=80,
                doc_nro=digits_only(invoice.get("customer_cuit")),
                condicion_iva_receptor_id=config.receiver_iva_condition_id,
                imp_neto=Decimal("0.00"),
                imp_iva=Decimal("0.00"),
                imp_total=Decimal("0.00"),
                iva=[],
                items=[],
            )
        else:
            arca_request = build_arca_invoice_request(
                invoice,
                repository.get_invoice_tax_breakdown(invoice_id),
                point_of_sale=config.point_of_sale,
                receiver_iva_condition_id=config.receiver_iva_condition_id,
            )
    except ValueError:
        repository.release_invoice_arca_authorization(invoice_id, "draft")
        raise

    arca_request_id = repository.create_arca_request(
        invoice_id=invoice_id,
        operation="FECAESolicitar",
        environment=config.environment,
        sanitized_request=sanitized_wsfe_payload(arca_request),
    )

    try:
        response = ArcaClient(config).authorize_invoice(arca_request)
    except (ArcaDisabledError, ArcaNotConfiguredError) as error:
        message = str(error) or "ARCA no configurado"
        repository.update_arca_request(arca_request_id, status="error", sanitized_response={"error": message}, error_code="ARCA_NOT_CONFIGURED", error_message=message)
        repository.update_invoice_arca_status(invoice_id, fiscal_status="error", arca_environment=config.environment, arca_cuit_emisor=config.cuit, arca_cbte_tipo=arca_request.cbte_tipo, arca_concepto=arca_request.concepto, arca_doc_tipo=arca_request.doc_tipo, arca_doc_nro=arca_request.doc_nro, arca_point_of_sale=arca_request.point_of_sale, arca_request_id=arca_request_id, arca_error_code="ARCA_NOT_CONFIGURED", arca_error_message=message)
        raise
    except (ArcaRejectedError, ArcaTechnicalError, RuntimeError) as error:
        message = str(error) or "ARCA rechazo la solicitud"
        status = arca_error_status(error)
        repository.update_arca_request(arca_request_id, status=status, sanitized_response={"error": message}, error_code="ARCA_ERROR", error_message=message)
        repository.update_invoice_arca_status(invoice_id, fiscal_status=status, arca_environment=config.environment, arca_cuit_emisor=config.cuit, arca_cbte_tipo=arca_request.cbte_tipo, arca_concepto=arca_request.concepto, arca_doc_tipo=arca_request.doc_tipo, arca_doc_nro=arca_request.doc_nro, arca_point_of_sale=arca_request.point_of_sale, arca_request_id=arca_request_id, arca_error_code="ARCA_ERROR", arca_error_message=message)
        raise

    if response.get("result") == "DRY_RUN":
        repository.update_arca_request(arca_request_id, status="pending", sanitized_response=sanitized_arca_response(response))
        repository.release_invoice_arca_authorization(invoice_id, "draft")
        return {"invoice_id": invoice_id, "fiscal_status": "draft", "arca_request_id": arca_request_id, "message": "Validacion ARCA OK. No se genero comprobante porque ARCA_DRY_RUN esta activo."}

    repository.update_arca_request(arca_request_id, status="authorized", sanitized_response=sanitized_arca_response(response))
    repository.update_invoice_arca_status(
        invoice_id,
        fiscal_status="authorized",
        arca_environment=config.environment,
        arca_cuit_emisor=config.cuit,
        arca_cbte_tipo=arca_request.cbte_tipo,
        arca_concepto=arca_request.concepto,
        arca_doc_tipo=arca_request.doc_tipo,
        arca_doc_nro=arca_request.doc_nro,
        arca_point_of_sale=arca_request.point_of_sale,
        arca_request_id=arca_request_id,
        arca_invoice_number=int(response["invoice_number"]) if response.get("invoice_number") is not None else None,
        arca_cae=str(response["cae"]) if response.get("cae") is not None else None,
        arca_cae_expires_at=response.get("cae_expires_at"),
        arca_result="HOMOLOGACION" if not config.mark_authorized else str(response["result"]) if response.get("result") is not None else None,
        arca_observations=response.get("observations"),
    )
    return {"invoice_id": invoice_id, "fiscal_status": "authorized", "arca_request_id": arca_request_id, "message": "Comprobante autorizado en homologacion." if not config.mark_authorized else "Factura autorizada en ARCA"}

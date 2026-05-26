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
        is_manual_fiscal_item = item.get("product_id") is None and item.get("net_amount") is not None
        if is_manual_fiscal_item:
            net_amount = money_decimal(item.get("net_amount"))
        else:
            net_amount = money_decimal(item.get("effective_total") if item.get("effective_total") is not None else item.get("net_amount") if item.get("net_amount") is not None else item.get("total"))
        iva_amount = money_decimal(item.get("iva_amount") if item.get("iva_amount") is not None else net_amount * Decimal(str(iva_rate)))
        fiscal_total = money_decimal(item.get("fiscal_total") if item.get("fiscal_total") is not None else net_amount + iva_amount)
        unit_price = money_decimal((net_amount / quantity) if is_manual_fiscal_item else item.get("unit_price"))
        gross = money_decimal(net_amount if is_manual_fiscal_item else item.get("gross"))
        discount_amount = Decimal("0.00") if is_manual_fiscal_item else money_decimal(
            item.get("effective_discount") if item.get("effective_discount") is not None else max(Decimal("0"), gross - net_amount)
        )
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
    fiscal_snapshot = invoice.get("customer_fiscal_snapshot") if isinstance(invoice.get("customer_fiscal_snapshot"), dict) else {}
    doc_nro = digits_only(fiscal_snapshot.get("doc_nro") or invoice.get("customer_cuit"))
    if len(doc_nro) != 11:
        raise ValueError("Cliente con CUIT invalido")
    resolved_iva_condition_id = int(fiscal_snapshot.get("condicion_iva_receptor_id") or receiver_iva_condition_id)
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
    cbte_tipo = 3 if str(invoice.get("document_type") or "").upper() == "NOTA_CREDITO" else 1
    related_invoice = invoice.get("related_invoice") or {}
    associated_cbte_tipo = int(related_invoice.get("arca_cbte_tipo") or 1) if cbte_tipo == 3 else None
    associated_point_of_sale = int(related_invoice.get("arca_point_of_sale") or point_of_sale) if cbte_tipo == 3 else None
    associated_invoice_number = int(related_invoice.get("arca_invoice_number") or 0) if cbte_tipo == 3 else None
    if cbte_tipo == 3 and not associated_invoice_number:
        raise ValueError("La nota de crédito fiscal requiere una factura ARCA asociada")
    return ArcaInvoiceRequest(
        invoice_id=int(invoice["id"]),
        cbte_date=cbte_date,
        point_of_sale=point_of_sale,
        cbte_tipo=cbte_tipo,
        concepto=1,
        doc_tipo=80,
        doc_nro=doc_nro,
        condicion_iva_receptor_id=resolved_iva_condition_id,
        imp_neto=imp_neto,
        imp_iva=imp_iva,
        imp_total=money_decimal(imp_neto + imp_iva),
        iva=iva_items,
        items=arca_items,
        associated_cbte_tipo=associated_cbte_tipo,
        associated_point_of_sale=associated_point_of_sale,
        associated_invoice_number=associated_invoice_number,
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
        "CbtesAsoc": [{"Tipo": request.associated_cbte_tipo, "PtoVta": request.associated_point_of_sale, "Nro": request.associated_invoice_number}] if request.associated_invoice_number else [],
    }


def sanitized_arca_response(response: dict[str, object]) -> dict[str, object]:
    return {key: (value.isoformat() if hasattr(value, "isoformat") else value) for key, value in response.items()}


def authorized_status_for_environment(config) -> str:
    return "authorized" if config.environment == "produccion" else "authorized_homologation"


def minimal_arca_request_from_attempt(invoice: dict, arca_request: dict, config) -> ArcaInvoiceRequest:
    fiscal_snapshot = invoice.get("customer_fiscal_snapshot") if isinstance(invoice.get("customer_fiscal_snapshot"), dict) else {}
    return ArcaInvoiceRequest(
        invoice_id=int(invoice["id"]),
        cbte_date=date.today(),
        point_of_sale=int(arca_request.get("point_of_sale") or invoice.get("arca_point_of_sale") or config.point_of_sale or 0),
        cbte_tipo=int(arca_request.get("cbte_tipo") or invoice.get("arca_cbte_tipo") or (3 if str(invoice.get("document_type") or "").upper() == "NOTA_CREDITO" else 1)),
        concepto=int(invoice.get("arca_concepto") or 1),
        doc_tipo=int(invoice.get("arca_doc_tipo") or 80),
        doc_nro=digits_only(invoice.get("arca_doc_nro") or fiscal_snapshot.get("doc_nro") or invoice.get("customer_cuit")),
        condicion_iva_receptor_id=int(fiscal_snapshot.get("condicion_iva_receptor_id") or config.receiver_iva_condition_id),
        imp_neto=Decimal("0.00"),
        imp_iva=Decimal("0.00"),
        imp_total=Decimal("0.00"),
        iva=[],
        items=[],
    )


def persist_authorized_response(repository, invoice: dict, arca_request: ArcaInvoiceRequest, arca_request_id: int, config, response: dict[str, object]) -> dict[str, object]:
    next_status = authorized_status_for_environment(config)
    repository.update_arca_request(arca_request_id, status="authorized", sanitized_response=sanitized_arca_response(response))
    repository.update_invoice_arca_status(
        int(invoice["id"]),
        fiscal_status=next_status,
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
        arca_result="HOMOLOGACION" if config.environment == "homologacion" else str(response["result"]) if response.get("result") is not None else None,
        arca_observations=response.get("observations"),
    )
    return {"invoice_id": int(invoice["id"]), "fiscal_status": next_status, "arca_request_id": arca_request_id, "message": "Comprobante autorizado en homologacion." if config.environment == "homologacion" else "Factura autorizada en ARCA"}


def recover_authorization(repository, invoice_id: int, *, invoice: dict | None = None, arca_request: dict | None = None) -> dict[str, object] | None:
    config = get_arca_config()
    invoice = invoice or repository.get_invoice_detail(invoice_id)
    if not invoice:
        raise ValueError("Factura no encontrada")
    arca_request = arca_request or repository.get_current_arca_request(invoice_id)
    if not arca_request or not arca_request.get("cbte_number"):
        return None
    arca_invoice_request = minimal_arca_request_from_attempt(invoice, arca_request, config)
    arca_request_id = int(arca_request["id"])
    cbte_number = int(arca_request["cbte_number"])
    response = ArcaClient(config).recover_invoice(arca_invoice_request, cbte_number)
    if response:
        return persist_authorized_response(repository, invoice, arca_invoice_request, arca_request_id, config, response)
    message = "No se encontro comprobante autorizado para el intento vigente"
    repository.update_arca_request(arca_request_id, status="authorization_failed", sanitized_response={"recovered": False, "cbte_number": cbte_number}, error_code="ARCA_NOT_RECOVERED", error_message=message)
    repository.update_invoice_arca_status(invoice_id, fiscal_status="authorization_failed", arca_environment=config.environment, arca_cuit_emisor=config.cuit, arca_cbte_tipo=arca_invoice_request.cbte_tipo, arca_concepto=arca_invoice_request.concepto, arca_doc_tipo=arca_invoice_request.doc_tipo, arca_doc_nro=arca_invoice_request.doc_nro, arca_point_of_sale=arca_invoice_request.point_of_sale, arca_request_id=arca_request_id, arca_error_code="ARCA_NOT_RECOVERED", arca_error_message=message)
    return None


def authorize_invoice_in_arca(repository, invoice_id: int) -> dict[str, object]:
    invoice = repository.get_invoice_detail(invoice_id)
    if not invoice:
        raise ValueError("Factura no encontrada")
    if invoice.get("arca_cae") and invoice.get("arca_invoice_number"):
        return {"invoice_id": invoice_id, "fiscal_status": invoice.get("fiscal_status") or "draft", "arca_request_id": invoice.get("arca_request_id"), "message": "La factura ya tiene CAE y numero ARCA."}
    fiscal_status = str(invoice.get("fiscal_status") or "")
    if fiscal_status == "authorizing":
        raise ArcaAuthorizationConflict("La factura fiscal ya se esta autorizando")
    if fiscal_status == "authorized":
        raise ValueError("La factura fiscal ya esta autorizada")
    if fiscal_status not in {"draft", "authorization_failed", "rejected", "error"}:
        raise ValueError("Solo se pueden autorizar facturas fiscales")
    if str(invoice.get("split_kind") or "") != "fiscal" and not bool(invoice.get("declared")):
        raise ValueError("Solo se pueden autorizar facturas fiscales")
    current_arca_request = repository.get_current_arca_request(invoice_id)
    if current_arca_request and current_arca_request.get("cbte_number"):
        recovered = recover_authorization(repository, invoice_id, invoice=invoice, arca_request=current_arca_request)
        if recovered:
            return recovered
        raise ValueError("Existe un intento ARCA con numero asignado sin conciliar; no se reintenta FECAESolicitar")
    if not repository.reserve_invoice_arca_authorization(invoice_id):
        current_invoice = repository.get_invoice_detail(invoice_id)
        if current_invoice and current_invoice.get("arca_cae") and current_invoice.get("arca_invoice_number"):
            return {"invoice_id": invoice_id, "fiscal_status": current_invoice.get("fiscal_status") or "draft", "arca_request_id": current_invoice.get("arca_request_id"), "message": "La factura ya tiene CAE y numero ARCA."}
        raise ArcaAuthorizationConflict("La factura fiscal ya se esta autorizando")

    invoice = repository.get_invoice_detail(invoice_id) or invoice
    if str(invoice.get("document_type") or "").upper() == "NOTA_CREDITO":
        related_invoice_id = invoice.get("related_invoice_id")
        related_invoice = repository.get_invoice_detail(int(related_invoice_id)) if related_invoice_id else None
        if not related_invoice or not related_invoice.get("arca_invoice_number"):
            repository.release_invoice_arca_authorization(invoice_id, "draft")
            raise ValueError("La nota de crédito fiscal requiere una factura ARCA asociada")
        invoice["related_invoice"] = related_invoice
    config = get_arca_config()
    try:
        if not config.is_configured:
            arca_request = ArcaInvoiceRequest(
                invoice_id=invoice_id,
                cbte_date=date.today(),
                point_of_sale=config.point_of_sale or 0,
                cbte_tipo=3 if str(invoice.get("document_type") or "").upper() == "NOTA_CREDITO" else 1,
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

    try:
        cbte_number = None
        client = ArcaClient(config)
        if config.is_configured:
            cbte_number = client.get_next_number(arca_request)

        sanitized_request = sanitized_wsfe_payload(arca_request)
        if cbte_number is not None:
            sanitized_request["CbteNro"] = cbte_number
        arca_request_id = repository.create_arca_request(
            invoice_id=invoice_id,
            operation="FECAESolicitar",
            environment=config.environment,
            sanitized_request=sanitized_request,
            issuer_cuit=config.cuit or None,
            point_of_sale=arca_request.point_of_sale or None,
            cbte_tipo=arca_request.cbte_tipo,
            cbte_number=None if config.dry_run else cbte_number,
            idempotency_key=f"invoice:{invoice_id}:{config.environment}:{arca_request.point_of_sale}:{arca_request.cbte_tipo}",
            soap_action="FECAESolicitar",
        )
    except Exception:
        repository.release_invoice_arca_authorization(invoice_id, "error")
        raise

    try:
        response = client.authorize_invoice(arca_request, cbte_number=cbte_number)
    except (ArcaDisabledError, ArcaNotConfiguredError) as error:
        message = str(error) or "ARCA no configurado"
        repository.update_arca_request(arca_request_id, status="error", sanitized_response={"error": message}, error_code="ARCA_NOT_CONFIGURED", error_message=message)
        repository.update_invoice_arca_status(invoice_id, fiscal_status="error", arca_environment=config.environment, arca_cuit_emisor=config.cuit, arca_cbte_tipo=arca_request.cbte_tipo, arca_concepto=arca_request.concepto, arca_doc_tipo=arca_request.doc_tipo, arca_doc_nro=arca_request.doc_nro, arca_point_of_sale=arca_request.point_of_sale, arca_request_id=arca_request_id, arca_error_code="ARCA_NOT_CONFIGURED", arca_error_message=message)
        raise
    except ArcaRejectedError as error:
        message = str(error) or "ARCA rechazo la solicitud"
        repository.update_arca_request(arca_request_id, status="rejected", sanitized_response={"error": message}, error_code="ARCA_REJECTED", error_message=message)
        repository.update_invoice_arca_status(invoice_id, fiscal_status="rejected", arca_environment=config.environment, arca_cuit_emisor=config.cuit, arca_cbte_tipo=arca_request.cbte_tipo, arca_concepto=arca_request.concepto, arca_doc_tipo=arca_request.doc_tipo, arca_doc_nro=arca_request.doc_nro, arca_point_of_sale=arca_request.point_of_sale, arca_request_id=arca_request_id, arca_error_code="ARCA_REJECTED", arca_error_message=message)
        raise
    except (ArcaTechnicalError, RuntimeError) as error:
        message = str(error) or "ARCA rechazo la solicitud"
        if cbte_number is not None and "WSAA" not in message:
            recovered = recover_authorization(repository, invoice_id, invoice=invoice, arca_request={"id": arca_request_id, "point_of_sale": arca_request.point_of_sale, "cbte_tipo": arca_request.cbte_tipo, "cbte_number": cbte_number})
            if recovered:
                return recovered
            raise ArcaTechnicalError("Error tecnico ARCA; intento no conciliado, no reintentar sin resolver") from error
        repository.update_arca_request(arca_request_id, status="error", sanitized_response={"error": message}, error_code="ARCA_ERROR", error_message=message)
        repository.update_invoice_arca_status(invoice_id, fiscal_status="error", arca_environment=config.environment, arca_cuit_emisor=config.cuit, arca_cbte_tipo=arca_request.cbte_tipo, arca_concepto=arca_request.concepto, arca_doc_tipo=arca_request.doc_tipo, arca_doc_nro=arca_request.doc_nro, arca_point_of_sale=arca_request.point_of_sale, arca_request_id=arca_request_id, arca_error_code="ARCA_ERROR", arca_error_message=message)
        raise

    if response.get("result") == "DRY_RUN":
        repository.update_arca_request(arca_request_id, status="pending", sanitized_response=sanitized_arca_response(response))
        repository.release_invoice_arca_authorization(invoice_id, "draft")
        return {"invoice_id": invoice_id, "fiscal_status": "draft", "arca_request_id": arca_request_id, "message": "Validacion ARCA OK. No se genero comprobante porque ARCA_DRY_RUN esta activo."}

    return persist_authorized_response(repository, invoice, arca_request, arca_request_id, config, response)

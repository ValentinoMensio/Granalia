from __future__ import annotations

import math
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from ...dependencies import current_role, get_repository, require_admin, validate_invoice_authorization_password
from ...schemas import ArcaAuthorizationOut, AuthorizationPayload, InvoiceCreateOut, InvoiceDetailOut, InvoiceListItemOut, InvoiceRequest, StatusResponse
from ...services.arca import ArcaClient, ArcaDisabledError, ArcaNotConfiguredError, ArcaRejectedError, ArcaTechnicalError, get_arca_config
from ...services.arca.models import ArcaInvoiceItem, ArcaInvoiceRequest, ArcaIvaItem
from ...services.pdf import build_invoice_pdf
from ...services.invoicing import generate_invoice_document


router = APIRouter(prefix="/api/invoices", tags=["invoices"])
OPERATOR_HISTORY_DAYS = 7


def operator_min_order_date() -> date:
    return date.today() - timedelta(days=OPERATOR_HISTORY_DAYS - 1)


def ensure_invoice_visible_for_role(invoice: dict, role: str) -> None:
    if role != "operator":
        return
    if str(invoice.get("order_date") or "") < operator_min_order_date().isoformat():
        raise HTTPException(status_code=403, detail="Los operadores solo pueden ver facturas de los últimos 7 días")


def catalog_with_invoice_history(catalog: list[dict], invoice: dict) -> list[dict]:
    next_catalog = [{**product, "offerings": [dict(offering) for offering in product.get("offerings", [])]} for product in catalog]
    products_by_id = {str(product.get("id")): product for product in next_catalog}

    for item in invoice.get("items", []):
        product_id = item.get("product_id")
        offering_id = item.get("offering_id")
        if not product_id or not offering_id:
            continue

        product_key = str(product_id)
        product = products_by_id.get(product_key)
        if not product:
            product = {
                "id": product_id,
                "name": item.get("product_name") or "Producto anterior",
                "aliases": [],
                "offerings": [],
            }
            next_catalog.append(product)
            products_by_id[product_key] = product

        if any(str(offering.get("id")) == str(offering_id) for offering in product.get("offerings", [])):
            continue

        product["offerings"].append(
            {
                "id": offering_id,
                "label": item.get("offering_label") or item.get("label") or "Presentación anterior",
                "price": int(item.get("unit_price") or 0),
            }
        )
    return next_catalog


def normalize_lookup(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def find_catalog_product(catalog: list[dict], product_id: int | None = None, product_name: str = "") -> dict | None:
    if product_id is not None:
        match = next((item for item in catalog if str(item.get("id")) == str(product_id)), None)
        if match:
            return match
    normalized_name = normalize_lookup(product_name)
    return next((item for item in catalog if normalize_lookup(item.get("name")) == normalized_name), None)


def find_catalog_offering(product: dict | None, offering_id: int | None = None, offering_label: str = "") -> dict | None:
    if not product:
        return None
    offerings = product.get("offerings", [])
    if offering_id is not None:
        match = next((item for item in offerings if str(item.get("id")) == str(offering_id)), None)
        if match:
            return match
    normalized_label = normalize_lookup(offering_label)
    return next((item for item in offerings if normalize_lookup(item.get("label")) == normalized_label), None)


def split_quantity(value: object, declared_percentage: float) -> tuple[int, int]:
    quantity = float(value or 0)
    if quantity < 0 or not quantity.is_integer():
        raise ValueError("El modo dividido solo acepta cantidades enteras")
    declared_quantity = math.ceil(quantity * declared_percentage / 100)
    return int(quantity) - declared_quantity, declared_quantity


def order_with_items(order: dict, *, price_list_id: int | None, declared: bool, items: list[dict]) -> dict:
    return {
        **order,
        "price_list_id": price_list_id,
        "declared": declared,
        "items": items,
    }


def fiscalize_snapshot(snapshot: dict, catalog: list[dict]) -> dict:
    products_by_id = {str(product.get("id")): product for product in catalog}
    rows = []
    for row in snapshot.get("rows", []):
        next_row = dict(row)
        product = products_by_id.get(str(row.get("product_id") or ""))
        if not product:
            raise ValueError(f"Producto fiscal no encontrado para {row.get('product_name') or row.get('label')}")
        iva_rate = product.get("iva_rate")
        if iva_rate is None:
            raise ValueError(f"Falta configurar IVA fiscal para {product.get('name')}")
        next_row["iva_rate"] = float(iva_rate)
        rows.append(next_row)
    return {**snapshot, "rows": rows}


def money_decimal(value: object) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def digits_only(value: object) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def arca_iva_id_for_rate(value: object) -> int:
    return 4 if Decimal(str(value)) == Decimal("0.105") else 5


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


def sanitized_arca_payload(request: ArcaInvoiceRequest) -> dict[str, object]:
    return {
        "invoice_id": request.invoice_id,
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
        "Items": [
            {
                "codigo": item.code,
                "descripcion": item.description,
                "cantidad": str(item.quantity),
                "codigoUnidadMedida": item.unit_code,
                "precioUnitario": str(item.unit_price),
                "importeBonificacion": str(item.discount_amount),
                "codigoCondicionIVA": item.iva_id,
                "importeIVA": str(item.iva_amount),
                "importeItem": str(item.item_total),
            }
            for item in request.items
        ],
    }


def sanitized_wsfe_payload(request: ArcaInvoiceRequest) -> dict[str, object]:
    return {
        "invoice_id": request.invoice_id,
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


def ensure_invoice_authorizable(invoice: dict) -> None:
    fiscal_status = str(invoice.get("fiscal_status") or "")
    if fiscal_status == "authorizing":
        raise HTTPException(status_code=409, detail="La factura fiscal ya se esta autorizando")
    if fiscal_status == "authorized":
        raise HTTPException(status_code=400, detail="La factura fiscal ya esta autorizada")
    if fiscal_status not in {"draft", "rejected", "error"}:
        raise HTTPException(status_code=400, detail="Solo se pueden autorizar facturas fiscales")
    if str(invoice.get("split_kind") or "") != "fiscal" and not bool(invoice.get("declared")):
        raise HTTPException(status_code=400, detail="Solo se pueden autorizar facturas fiscales")


def arca_error_status(error: Exception) -> str:
    if isinstance(error, (ArcaDisabledError, ArcaNotConfiguredError)):
        return "error"
    if isinstance(error, ArcaTechnicalError):
        return "error"
    return "rejected"


def build_split_orders(order: dict, internal_catalog: list[dict], fiscal_catalog: list[dict]) -> tuple[dict, dict]:
    declared_percentage = float(order.get("declared_percentage") or 0)
    internal_items: list[dict] = []
    fiscal_items: list[dict] = []

    for item in order.get("items", []):
        product = find_catalog_product(internal_catalog, item.get("product_id"))
        offering = find_catalog_offering(product, item.get("offering_id"))
        if not product or not offering:
            raise ValueError("Producto o presentacion interna no encontrada")

        fiscal_product = find_catalog_product(fiscal_catalog, product_name=str(product.get("name") or ""))
        fiscal_offering = find_catalog_offering(fiscal_product, offering_label=str(offering.get("label") or ""))
        if not fiscal_product:
            raise ValueError(f"Falta el producto {product.get('name')} en la lista declarada")
        if not fiscal_offering:
            raise ValueError(f"Falta la presentacion {offering.get('label')} de {product.get('name')} en la lista declarada")
        if fiscal_product.get("iva_rate") is None:
            raise ValueError(f"Falta configurar IVA fiscal para {fiscal_product.get('name')}")

        internal_quantity, fiscal_quantity = split_quantity(item.get("quantity"), declared_percentage)
        internal_bonus = int(item.get("bonus_quantity") or 0)
        if internal_quantity > 0 or internal_bonus > 0:
            internal_items.append({**item, "quantity": internal_quantity, "bonus_quantity": internal_bonus})
        if fiscal_quantity > 0:
            fiscal_items.append(
                {
                    **item,
                    "product_id": int(fiscal_product["id"]),
                    "offering_id": int(fiscal_offering["id"]),
                    "quantity": fiscal_quantity,
                    "bonus_quantity": 0,
                    "unit_price": int(fiscal_offering.get("price") or 0),
                }
            )

    if not internal_items and not fiscal_items:
        raise ValueError("No hay cantidades para generar")
    return (
        order_with_items(order, price_list_id=order.get("internal_price_list_id") or order.get("price_list_id"), declared=False, items=internal_items),
        order_with_items(order, price_list_id=order.get("fiscal_price_list_id"), declared=True, items=fiscal_items),
    )


def ensure_invoice_editable(invoice: dict) -> None:
    if str(invoice.get("fiscal_status") or "") == "authorized":
        raise HTTPException(status_code=400, detail="No se puede editar un comprobante fiscal autorizado")


def ensure_invoice_deletable(invoice: dict) -> None:
    if str(invoice.get("fiscal_status") or "") == "authorized" and str(invoice.get("arca_environment") or "") != "homologacion":
        raise HTTPException(status_code=400, detail="No se puede eliminar un comprobante fiscal autorizado")


def ensure_batch_editable(repository, batch_id: int | None) -> None:
    if not batch_id:
        return
    statuses = repository.list_batch_invoice_statuses(batch_id)
    if any(str(item.get("fiscal_status") or "") == "authorized" and str(item.get("arca_environment") or "") != "homologacion" for item in statuses):
        raise HTTPException(status_code=400, detail="No se puede editar un batch split con parte fiscal autorizada")


def build_and_save_split(repository, order: dict, profile: dict, *, update_customer: bool, replace_batch_id: int | None = None) -> InvoiceCreateOut:
    internal_price_list_id = order.get("internal_price_list_id") or order.get("price_list_id")
    fiscal_price_list_id = order.get("fiscal_price_list_id")
    if not fiscal_price_list_id:
        raise ValueError("Selecciona una lista declarada")
    internal_catalog = repository.get_catalog_for_price_list(int(internal_price_list_id)) if internal_price_list_id else repository.get_active_catalog()
    fiscal_catalog = repository.get_catalog_for_price_list(int(fiscal_price_list_id))
    internal_order, fiscal_order = build_split_orders(order, internal_catalog, fiscal_catalog)
    declared_percentage = float(order.get("declared_percentage") or 0)
    batch_invoices = []
    response_invoices = []
    if internal_order.get("items"):
        internal_filename, internal_xlsx, internal_snapshot = generate_invoice_document(internal_order, profile, internal_catalog)
        batch_invoices.append({"order": internal_order, "snapshot": internal_snapshot, "filename": internal_filename, "xlsx_bytes": internal_xlsx, "split_kind": "internal", "split_percentage": 100 - declared_percentage, "fiscal_status": "internal"})
    if fiscal_order.get("items"):
        fiscal_filename, fiscal_xlsx, fiscal_snapshot = generate_invoice_document(fiscal_order, profile, fiscal_catalog)
        fiscal_snapshot = fiscalize_snapshot(fiscal_snapshot, fiscal_catalog)
        batch_invoices.append({"order": fiscal_order, "snapshot": fiscal_snapshot, "filename": fiscal_filename, "xlsx_bytes": fiscal_xlsx, "split_kind": "fiscal", "split_percentage": declared_percentage, "fiscal_status": "draft"})
    if not batch_invoices:
        raise ValueError("No hay cantidades para generar")
    batch_id, invoice_ids = repository.save_invoice_batch(
        batch={"client_name": order["client_name"], "order_date": order["date"], "billing_mode": "split", "declared_percentage": declared_percentage, "internal_percentage": 100 - declared_percentage, "internal_price_list_id": internal_price_list_id, "fiscal_price_list_id": fiscal_price_list_id, "transport": order.get("transport") or profile.get("transport") or "", "secondary_line": order.get("secondary_line") or profile.get("secondary_line") or "", "notes": order.get("notes") or profile.get("notes") or [], "profile": profile},
        invoices=batch_invoices,
        update_customer=update_customer,
        replace_batch_id=replace_batch_id,
    )
    for invoice_id, doc in zip(invoice_ids, batch_invoices):
        response_invoices.append({"invoice_id": invoice_id, "split_kind": doc.get("split_kind"), "fiscal_status": doc.get("fiscal_status")})
    first_doc = batch_invoices[0]
    first_snapshot = first_doc["snapshot"]
    first_invoice_id = invoice_ids[0]
    return InvoiceCreateOut.model_validate({"invoice_id": first_invoice_id, "batch_id": batch_id, "invoices": response_invoices, "filename": first_doc["filename"], "download_url": f"/api/invoices/{first_invoice_id}/xlsx", "summary": first_snapshot["summary"]})


@router.get("", response_model=list[InvoiceListItemOut])
def invoices(limit: int = Query(default=500, ge=1, le=10000), role: str = Depends(current_role)) -> list[InvoiceListItemOut]:
    date_from = operator_min_order_date() if role == "operator" else None
    return [InvoiceListItemOut.model_validate(item) for item in get_repository().list_invoices(limit=limit, date_from=date_from)]


@router.get("/stats/items")
def invoice_item_stats(_: str = Depends(require_admin)) -> list[dict[str, object]]:
    return get_repository().list_invoice_item_stats()


@router.get("/{invoice_id}", response_model=InvoiceDetailOut)
def invoice_detail(invoice_id: int, role: str = Depends(current_role)) -> InvoiceDetailOut:
    invoice = get_repository().get_invoice_detail(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    ensure_invoice_visible_for_role(invoice, role)
    return InvoiceDetailOut.model_validate(invoice)


@router.get("/{invoice_id}/xlsx")
def download_invoice(invoice_id: int, role: str = Depends(current_role)) -> Response:
    repository = get_repository()
    invoice_detail_data = repository.get_invoice_detail(invoice_id)
    if not invoice_detail_data:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    ensure_invoice_visible_for_role(invoice_detail_data, role)
    invoice = repository.get_invoice_file(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    return Response(
        content=invoice["xlsx_data"],
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{invoice["output_filename"]}"'},
    )


@router.get("/{invoice_id}/pdf")
def download_invoice_pdf(invoice_id: int, role: str = Depends(current_role)) -> Response:
    invoice = get_repository().get_invoice_detail(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    ensure_invoice_visible_for_role(invoice, role)
    pdf_bytes = build_invoice_pdf(invoice)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="factura-{invoice_id}.pdf"'},
    )


@router.post("", response_model=InvoiceCreateOut)
def create_invoice(payload: InvoiceRequest, role: str = Depends(current_role)) -> InvoiceCreateOut:
    repository = get_repository()
    order = payload.order.model_dump()
    profile = payload.profile.model_dump()
    billing_mode = str(order.get("billing_mode") or ("fiscal_only" if order.get("declared") else "internal_only"))
    try:
        if billing_mode == "internal_only":
            order["declared"] = False
            order["price_list_id"] = order.get("internal_price_list_id") or order.get("price_list_id")
            catalog = repository.get_catalog_for_price_list(int(order["price_list_id"])) if order.get("price_list_id") else repository.get_active_catalog()
            filename, xlsx_bytes, snapshot = generate_invoice_document(order, profile, catalog)
            invoice_id = repository.save_invoice(order, profile, snapshot, filename, xlsx_bytes, update_customer=role == "admin", split_kind="internal", fiscal_status="internal")
            return InvoiceCreateOut.model_validate({
                "invoice_id": invoice_id,
                "invoices": [{"invoice_id": invoice_id, "split_kind": "internal", "fiscal_status": "internal"}],
                "filename": filename,
                "download_url": f"/api/invoices/{invoice_id}/xlsx",
                "summary": snapshot["summary"],
            })

        if billing_mode == "fiscal_only":
            order["declared"] = True
            order["price_list_id"] = order.get("fiscal_price_list_id") or order.get("price_list_id")
            order["items"] = [{**item, "bonus_quantity": 0} for item in order.get("items", [])]
            catalog = repository.get_catalog_for_price_list(int(order["price_list_id"])) if order.get("price_list_id") else repository.get_active_catalog()
            filename, xlsx_bytes, snapshot = generate_invoice_document(order, profile, catalog)
            snapshot = fiscalize_snapshot(snapshot, catalog)
            invoice_id = repository.save_invoice(order, profile, snapshot, filename, xlsx_bytes, update_customer=role == "admin", split_kind="fiscal", fiscal_status="draft")
            return InvoiceCreateOut.model_validate({
                "invoice_id": invoice_id,
                "invoices": [{"invoice_id": invoice_id, "split_kind": "fiscal", "fiscal_status": "draft"}],
                "filename": filename,
                "download_url": f"/api/invoices/{invoice_id}/xlsx",
                "summary": snapshot["summary"],
            })

        return build_and_save_split(repository, order, profile, update_customer=role == "admin")
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/{invoice_id}/arca/authorize", response_model=ArcaAuthorizationOut)
def authorize_invoice_in_arca(invoice_id: int, payload: AuthorizationPayload, _: str = Depends(require_admin)) -> ArcaAuthorizationOut:
    validate_invoice_authorization_password(payload.password)
    repository = get_repository()
    invoice = repository.get_invoice_detail(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    if invoice.get("arca_cae") and invoice.get("arca_invoice_number"):
        return ArcaAuthorizationOut.model_validate({"invoice_id": invoice_id, "fiscal_status": "authorized", "arca_request_id": invoice.get("arca_request_id"), "message": "La factura ya tiene CAE y numero ARCA."})
    ensure_invoice_authorizable(invoice)
    if not repository.reserve_invoice_arca_authorization(invoice_id):
        current_invoice = repository.get_invoice_detail(invoice_id)
        if current_invoice and current_invoice.get("arca_cae") and current_invoice.get("arca_invoice_number"):
            return ArcaAuthorizationOut.model_validate({"invoice_id": invoice_id, "fiscal_status": "authorized", "arca_request_id": current_invoice.get("arca_request_id"), "message": "La factura ya tiene CAE y numero ARCA."})
        if current_invoice and str(current_invoice.get("fiscal_status") or "") == "authorizing":
            raise HTTPException(status_code=409, detail="La factura fiscal ya se esta autorizando")
        raise HTTPException(status_code=409, detail="No se pudo reservar la autorizacion ARCA")
    invoice = repository.get_invoice_detail(invoice_id) or invoice

    config = get_arca_config()
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
        try:
            arca_request = build_arca_invoice_request(
                invoice,
                repository.get_invoice_tax_breakdown(invoice_id),
                point_of_sale=config.point_of_sale,
                receiver_iva_condition_id=config.receiver_iva_condition_id,
            )
        except ValueError as error:
            repository.release_invoice_arca_authorization(invoice_id, "draft")
            raise HTTPException(status_code=400, detail=str(error)) from error

    sanitized_request = sanitized_wsfe_payload(arca_request)
    arca_request_id = repository.create_arca_request(
        invoice_id=invoice_id,
        operation="FECAESolicitar",
        environment=config.environment,
        sanitized_request=sanitized_request,
    )

    try:
        response = ArcaClient(config).authorize_invoice(arca_request)
    except (ArcaDisabledError, ArcaNotConfiguredError) as error:
        message = str(error) or "ARCA no configurado"
        sanitized_response = {"error": message}
        repository.update_arca_request(
            arca_request_id,
            status="error",
            sanitized_response=sanitized_response,
            error_code="ARCA_NOT_CONFIGURED",
            error_message=message,
        )
        repository.update_invoice_arca_status(
            invoice_id,
            fiscal_status="error",
            arca_environment=config.environment,
            arca_cuit_emisor=config.cuit,
            arca_cbte_tipo=arca_request.cbte_tipo,
            arca_concepto=arca_request.concepto,
            arca_doc_tipo=arca_request.doc_tipo,
            arca_doc_nro=arca_request.doc_nro,
            arca_point_of_sale=arca_request.point_of_sale,
            arca_request_id=arca_request_id,
            arca_error_code="ARCA_NOT_CONFIGURED",
            arca_error_message=message,
        )
        raise HTTPException(status_code=400, detail=message) from error
    except (ArcaRejectedError, ArcaTechnicalError, RuntimeError) as error:
        message = str(error) or "ARCA rechazo la solicitud"
        sanitized_response = {"error": message}
        status = arca_error_status(error)
        repository.update_arca_request(
            arca_request_id,
            status=status,
            sanitized_response=sanitized_response,
            error_code="ARCA_ERROR",
            error_message=message,
        )
        repository.update_invoice_arca_status(
            invoice_id,
            fiscal_status=status,
            arca_environment=config.environment,
            arca_cuit_emisor=config.cuit,
            arca_cbte_tipo=arca_request.cbte_tipo,
            arca_concepto=arca_request.concepto,
            arca_doc_tipo=arca_request.doc_tipo,
            arca_doc_nro=arca_request.doc_nro,
            arca_point_of_sale=arca_request.point_of_sale,
            arca_request_id=arca_request_id,
            arca_error_code="ARCA_ERROR",
            arca_error_message=message,
        )
        raise HTTPException(status_code=400, detail=message) from error

    if response.get("result") == "DRY_RUN":
        repository.update_arca_request(arca_request_id, status="pending", sanitized_response=sanitized_arca_response(response))
        repository.release_invoice_arca_authorization(invoice_id, "draft")
        return ArcaAuthorizationOut.model_validate({
            "invoice_id": invoice_id,
            "fiscal_status": "draft",
            "arca_request_id": arca_request_id,
            "message": "Validacion ARCA OK. No se genero comprobante porque ARCA_DRY_RUN esta activo.",
        })

    repository.update_arca_request(arca_request_id, status="authorized", sanitized_response=sanitized_arca_response(response))
    if not config.mark_authorized:
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
            arca_result="HOMOLOGACION",
            arca_observations=response.get("observations"),
        )
        return ArcaAuthorizationOut.model_validate({
            "invoice_id": invoice_id,
            "fiscal_status": "authorized",
            "arca_request_id": arca_request_id,
            "message": "Comprobante autorizado en homologacion.",
        })

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
        arca_result=str(response["result"]) if response.get("result") is not None else None,
        arca_observations=response.get("observations"),
    )
    return ArcaAuthorizationOut.model_validate({"invoice_id": invoice_id, "fiscal_status": "authorized", "arca_request_id": arca_request_id, "message": "Factura autorizada en ARCA"})


@router.put("/{invoice_id}", response_model=InvoiceCreateOut)
def update_invoice(invoice_id: int, payload: InvoiceRequest, _: str = Depends(require_admin)) -> InvoiceCreateOut:
    repository = get_repository()
    invoice = repository.get_invoice_detail(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    ensure_invoice_editable(invoice)
    batch_id = int(invoice["batch_id"]) if invoice.get("batch_id") is not None else None
    ensure_batch_editable(repository, batch_id)
    order = payload.order.model_dump()
    profile = payload.profile.model_dump()
    try:
        if batch_id is not None:
            if str(order.get("billing_mode") or "") != "split":
                raise ValueError("Para editar un batch split se debe regenerar el split completo")
            return build_and_save_split(repository, order, profile, update_customer=True, replace_batch_id=batch_id)

        base_catalog = repository.get_catalog_for_price_list(int(order["price_list_id"])) if order.get("price_list_id") else repository.get_active_catalog()
        catalog = catalog_with_invoice_history(base_catalog, invoice)
        filename, xlsx_bytes, snapshot = generate_invoice_document(order, profile, catalog)
        repository.update_invoice(invoice_id, order, profile, snapshot, filename, xlsx_bytes)
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return InvoiceCreateOut.model_validate({
        "invoice_id": invoice_id,
        "filename": filename,
        "download_url": f"/api/invoices/{invoice_id}/xlsx",
        "summary": snapshot["summary"],
    })


@router.delete("/{invoice_id}", response_model=StatusResponse)
def delete_invoice(invoice_id: int, _: str = Depends(require_admin)) -> StatusResponse:
    repository = get_repository()
    invoice = repository.get_invoice_detail(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    ensure_invoice_deletable(invoice)
    ensure_batch_editable(repository, int(invoice["batch_id"]) if invoice.get("batch_id") is not None else None)
    try:
        repository.delete_invoice(invoice_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return StatusResponse(status="deleted")

from __future__ import annotations

import math
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from ...dependencies import current_role, get_repository, require_admin, validate_invoice_authorization_password
from ...schemas import ArcaAuthorizationOut, AuthorizationPayload, CreditNoteRequest, InvoiceCreateOut, InvoiceDetailOut, InvoiceListItemOut, InvoiceRequest, StatusResponse
from ...services.arca import ArcaDisabledError, ArcaNotConfiguredError, ArcaRejectedError, ArcaTechnicalError
from ...services.arca.authorization import ArcaAuthorizationConflict, authorize_invoice_in_arca as authorize_invoice_service
from ...services.arca.padron import get_taxpayer_data, lookup_taxpayer_data
from ...services.pdf import build_invoice_pdf, invoice_pdf_filename
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


def catalog_with_invoice_history(catalog: list[dict], invoice: dict, order: dict | None = None) -> list[dict]:
    next_catalog = [{**product, "offerings": [dict(offering) for offering in product.get("offerings", [])]} for product in catalog]
    products_by_id = {str(product.get("id")): product for product in next_catalog}
    selected_labels = {
        (str(item.get("product_id") or ""), str(item.get("offering_id") or "")): str(item.get("offering_label") or "").strip()
        for item in (order or {}).get("items", [])
    }

    for item in invoice.get("items", []):
        product_id = item.get("product_id")
        offering_id = item.get("offering_id")
        if not product_id or not offering_id:
            continue

        product_key = str(product_id)
        offering_key = str(offering_id)
        historical_label = str(item.get("offering_label") or item.get("label") or "").strip()
        selected_label = selected_labels.get((product_key, offering_key), "")
        if selected_label and historical_label and selected_label != historical_label:
            continue

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
        else:
            product["name"] = item.get("product_name") or product.get("name")

        historical_offering = {
            "id": offering_id,
            "label": historical_label or "Presentación anterior",
            "price": int(item.get("unit_price") or 0),
            "net_weight_kg": float(item.get("offering_net_weight_kg") or item.get("net_weight_kg") or 0),
        }
        current_offerings = product.get("offerings", [])
        existing_index = next((index for index, offering in enumerate(current_offerings) if str(offering.get("id")) == str(offering_id)), None)
        if existing_index is not None:
            current_offerings[existing_index] = {**current_offerings[existing_index], **historical_offering}
            continue

        product["offerings"].append(historical_offering)
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


def profile_with_arca_taxpayer_data(profile: dict) -> dict:
    taxpayer = get_taxpayer_data(profile.get("cuit"))
    if not taxpayer:
        return profile
    return {
        **profile,
        "business_name": taxpayer.get("business_name") or profile.get("business_name") or profile.get("name") or "",
        "address": taxpayer.get("address") or profile.get("address") or "",
        "cuit": taxpayer.get("cuit") or profile.get("cuit") or "",
        "iva_condition": taxpayer.get("iva_condition") or profile.get("iva_condition") or "",
    }


def invoice_with_arca_taxpayer_data(invoice: dict) -> dict:
    if not (bool(invoice.get("declared")) or invoice.get("split_kind") == "fiscal"):
        return invoice
    taxpayer = get_taxpayer_data(invoice.get("customer_cuit") or invoice.get("arca_doc_nro"))
    if not taxpayer:
        return invoice
    return {
        **invoice,
        "customer_cuit": taxpayer.get("cuit") or invoice.get("customer_cuit"),
        "customer_business_name": taxpayer.get("business_name") or invoice.get("customer_business_name"),
        "customer_address": taxpayer.get("address") or invoice.get("customer_address"),
        "customer_iva_condition": taxpayer.get("iva_condition") or invoice.get("customer_iva_condition"),
    }


def fiscalize_snapshot(snapshot: dict, catalog: list[dict]) -> dict:
    products_by_id = {str(product.get("id")): product for product in catalog}
    rows = []
    for row in snapshot.get("rows", []):
        next_row = dict(row)
        if row.get("product_id") is None and row.get("iva_rate") is not None:
            rows.append(next_row)
            continue
        product = products_by_id.get(str(row.get("product_id") or ""))
        if not product:
            raise ValueError(f"Producto fiscal no encontrado para {row.get('product_name') or row.get('label')}")
        iva_rate = product.get("iva_rate")
        if iva_rate is None:
            raise ValueError(f"Falta configurar IVA fiscal para {product.get('name')}")
        next_row["iva_rate"] = float(iva_rate)
        rows.append(next_row)
    return {**snapshot, "rows": rows}


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


def is_credit_note(invoice: dict) -> bool:
    return str(invoice.get("document_type") or "").upper() == "NOTA_CREDITO"


def is_fiscal_invoice(invoice: dict) -> bool:
    return bool(invoice.get("declared")) or invoice.get("split_kind") == "fiscal"


def profile_from_invoice(invoice: dict) -> dict:
    return {
        "id": invoice.get("customer_id"),
        "name": invoice.get("client_name") or invoice.get("customer_name") or "Cliente",
        "cuit": invoice.get("customer_cuit") or "",
        "address": invoice.get("customer_address") or "",
        "business_name": invoice.get("customer_business_name") or "",
        "iva_condition": invoice.get("customer_iva_condition") or "",
        "email": invoice.get("customer_email") or "",
        "secondary_line": invoice.get("secondary_line") or "",
        "transport": invoice.get("transport") or "",
        "notes": invoice.get("notes") or [],
        "footer_discounts": invoice.get("footer_discounts") or [],
        "line_discounts_by_format": invoice.get("line_discounts_by_format") or {},
        "automatic_bonus_rules": [],
        "automatic_bonus_disables_line_discount": False,
        "source_count": 0,
    }


def money_decimal(value: object) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def empty_credit_note_snapshot(order: dict, profile: dict) -> dict:
    return {
        "rows": [],
        "summary": {"gross_total": 0, "discount_total": 0, "final_total": 0, "total_bultos": 0},
        "order": order,
        "profile": profile,
    }


def append_manual_credit_note_item(snapshot: dict, manual_item: object, *, fiscal: bool) -> None:
    if manual_item is None:
        return
    amount = money_decimal(manual_item.amount)
    if amount <= 0:
        raise ValueError("El importe manual debe ser mayor a cero")
    iva_rate = manual_item.iva_rate if fiscal else None
    if fiscal and iva_rate is None:
        raise ValueError("Seleccioná la alícuota de IVA para el concepto manual")
    row = {
        "product_id": None,
        "offering_id": None,
        "product_name": "",
        "offering_label": "",
        "offering_net_weight_kg": 0,
        "line_type": "sale",
        "discount_rate": 0,
        "label": manual_item.description,
        "quantity": 1,
        "unit_price": int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
        "gross": int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
        "discount": 0,
        "total": int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
    }
    if fiscal:
        rate = Decimal(str(iva_rate))
        row["iva_rate"] = float(rate)
        row["net_amount"] = amount
        row["iva_amount"] = float((Decimal(amount) * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        row["fiscal_total"] = float((Decimal(amount) * (Decimal("1") + rate)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    snapshot["rows"].append(row)
    rounded_amount = int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    snapshot["summary"]["gross_total"] = int(snapshot["summary"].get("gross_total") or 0) + rounded_amount
    snapshot["summary"]["final_total"] = int(snapshot["summary"].get("final_total") or 0) + rounded_amount
    snapshot["summary"]["total_bultos"] = float(snapshot["summary"].get("total_bultos") or 0) + 1


def build_credit_note_order(invoice: dict, payload: CreditNoteRequest, credited_quantities: dict[int, float]) -> tuple[dict, dict]:
    items_by_id = {int(item["id"]): item for item in invoice.get("items", [])}
    credit_items = []
    iva_by_key: dict[tuple[str, str], float] = {}
    for requested in payload.items:
        source_item = items_by_id.get(requested.invoice_item_id)
        if not source_item:
            raise ValueError("La línea seleccionada no pertenece a la factura")
        if str(source_item.get("line_type") or "sale") != "sale" or float(source_item.get("quantity") or 0) <= 0:
            raise ValueError("Solo se pueden acreditar líneas de venta")
        available = float(source_item.get("quantity") or 0) - float(credited_quantities.get(requested.invoice_item_id, 0) or 0)
        quantity = float(requested.quantity)
        if quantity > available + 0.000001:
            raise ValueError(f"La cantidad a acreditar de {source_item.get('label')} supera la disponible ({available:g})")
        credit_items.append({
            "product_id": int(source_item["product_id"]),
            "offering_id": int(source_item["offering_id"]),
            "offering_label": str(source_item.get("offering_label") or ""),
            "quantity": quantity,
            "bonus_quantity": 0,
            "unit_price": int(source_item.get("unit_price") or 0),
        })
        if source_item.get("iva_rate") is not None:
            iva_by_key[(str(source_item.get("product_id") or ""), str(source_item.get("offering_id") or ""))] = float(source_item["iva_rate"])
    if not credit_items and payload.manual_item is None:
        raise ValueError("Seleccioná al menos una línea para acreditar")
    order = {
        "client_name": invoice["client_name"],
        "date": payload.date,
        "price_list_id": invoice.get("price_list_id"),
        "billing_mode": "fiscal_only" if is_fiscal_invoice(invoice) else "internal_only",
        "declared": is_fiscal_invoice(invoice),
        "secondary_line": invoice.get("secondary_line") or "",
        "transport": invoice.get("transport") or "",
        "notes": [*(invoice.get("notes") or []), f"Nota de crédito por: {payload.reason}"],
        "items": credit_items,
    }
    return order, iva_by_key


def build_internal_credit_note_from_sources(repository, order: dict, profile: dict, *, credit_note_invoice_id: int | None = None) -> tuple[dict, list[dict[str, object]]]:
    customer_id = profile.get("id")
    if not customer_id:
        raise ValueError("Seleccioná un cliente histórico para generar una nota de crédito interna")
    available_items = repository.list_internal_credit_note_available_items(int(customer_id), credit_note_invoice_id=credit_note_invoice_id)
    available_by_id = {int(item["invoice_item_id"]): item for item in available_items}
    credit_items_by_key: dict[tuple[int, int, int], dict[str, object]] = {}
    source_links: list[dict[str, object]] = []
    requested_by_source: dict[int, float] = {}
    for requested in order.get("items", []):
        source_item_id = requested.get("source_invoice_item_id")
        if not source_item_id:
            raise ValueError("Seleccioná el remito/factura origen de cada producto a devolver")
        source_item_id = int(source_item_id)
        source = available_by_id.get(source_item_id)
        if not source:
            raise ValueError("La línea origen no está disponible para devolución")
        quantity = float(requested.get("quantity") or 0)
        available = float(source.get("available_quantity") or 0)
        if quantity <= 0:
            continue
        requested_total = requested_by_source.get(source_item_id, 0.0) + quantity
        if requested_total > available + 0.000001:
            raise ValueError(f"La cantidad a devolver de {source.get('label')} supera la disponible ({available:g})")
        requested_by_source[source_item_id] = requested_total
        product_id = int(source["product_id"])
        offering_id = int(source["offering_id"])
        unit_price = int(source.get("unit_price") or 0)
        key = (product_id, offering_id, unit_price)
        credit_item = credit_items_by_key.setdefault(
            key,
            {
                "product_id": product_id,
                "offering_id": offering_id,
                "offering_label": str(source.get("offering_label") or ""),
                "quantity": 0,
                "bonus_quantity": 0,
                "unit_price": unit_price,
            },
        )
        credit_item["quantity"] = float(credit_item["quantity"] or 0) + quantity
        source_links.append({
            "source_invoice_id": int(source["invoice_id"]),
            "source_invoice_item_id": source_item_id,
            "product_id": product_id,
            "offering_id": offering_id,
            "unit_price": unit_price,
            "quantity": quantity,
        })
    credit_items = list(credit_items_by_key.values())
    if not credit_items:
        raise ValueError("Seleccioná al menos un producto a devolver")
    return {**order, "items": credit_items, "declared": False}, source_links


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
        internal_snapshot = generate_invoice_document(internal_order, profile, internal_catalog)
        batch_invoices.append({"order": internal_order, "snapshot": internal_snapshot, "split_kind": "internal", "split_percentage": 100 - declared_percentage, "fiscal_status": "internal"})
    if fiscal_order.get("items"):
        fiscal_profile = profile_with_arca_taxpayer_data(profile)
        fiscal_snapshot = generate_invoice_document(fiscal_order, fiscal_profile, fiscal_catalog)
        fiscal_snapshot = fiscalize_snapshot(fiscal_snapshot, fiscal_catalog)
        batch_invoices.append({"order": fiscal_order, "profile": fiscal_profile, "snapshot": fiscal_snapshot, "split_kind": "fiscal", "split_percentage": declared_percentage, "fiscal_status": "draft"})
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
    first_snapshot = batch_invoices[0]["snapshot"]
    first_invoice_id = invoice_ids[0]
    return InvoiceCreateOut.model_validate({"invoice_id": first_invoice_id, "batch_id": batch_id, "invoices": response_invoices, "summary": first_snapshot["summary"]})


@router.get("", response_model=list[InvoiceListItemOut])
def invoices(limit: int = Query(default=500, ge=1, le=10000), role: str = Depends(current_role)) -> list[InvoiceListItemOut]:
    date_from = operator_min_order_date() if role == "operator" else None
    return [InvoiceListItemOut.model_validate(item) for item in get_repository().list_invoices(limit=limit, date_from=date_from)]


@router.get("/stats/items")
def invoice_item_stats(_: str = Depends(require_admin)) -> list[dict[str, object]]:
    return get_repository().list_invoice_item_stats()


@router.get("/arca/taxpayer/{cuit}")
def arca_taxpayer_lookup(cuit: str, _: str = Depends(require_admin)) -> dict[str, object]:
    return lookup_taxpayer_data(cuit)


@router.get("/internal-credit-note-items")
def internal_credit_note_items(
    customer_id: int = Query(..., ge=1),
    credit_note_invoice_id: int | None = Query(default=None, ge=1),
    _: str = Depends(current_role),
) -> list[dict[str, object]]:
    return get_repository().list_internal_credit_note_available_items(customer_id, credit_note_invoice_id=credit_note_invoice_id)


@router.get("/{invoice_id}", response_model=InvoiceDetailOut)
def invoice_detail(invoice_id: int, role: str = Depends(current_role)) -> InvoiceDetailOut:
    invoice = get_repository().get_invoice_detail(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    ensure_invoice_visible_for_role(invoice, role)
    return InvoiceDetailOut.model_validate(invoice)


@router.get("/{invoice_id}/pdf")
def download_invoice_pdf(invoice_id: int, role: str = Depends(current_role)) -> Response:
    invoice = get_repository().get_invoice_detail(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    ensure_invoice_visible_for_role(invoice, role)
    invoice = invoice_with_arca_taxpayer_data(invoice)
    pdf_bytes = build_invoice_pdf(invoice)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{invoice_pdf_filename(invoice)}"'},
    )


@router.post("", response_model=InvoiceCreateOut)
def create_invoice(payload: InvoiceRequest, role: str = Depends(current_role)) -> InvoiceCreateOut:
    repository = get_repository()
    order = payload.order.model_dump()
    profile = payload.profile.model_dump()
    billing_mode = str(order.get("billing_mode") or ("fiscal_only" if order.get("declared") else "internal_only"))
    try:
        if billing_mode == "internal_credit_note":
            order, source_links = build_internal_credit_note_from_sources(repository, order, profile)
            order["price_list_id"] = order.get("internal_price_list_id") or order.get("price_list_id")
            catalog = repository.get_catalog_for_price_list(int(order["price_list_id"])) if order.get("price_list_id") else repository.get_active_catalog()
            history_invoice = {"items": [
                {
                    "product_id": item["product_id"],
                    "offering_id": item["offering_id"],
                    "product_name": item.get("product_name") or item.get("label"),
                    "offering_label": item.get("offering_label"),
                    "unit_price": item.get("unit_price"),
                    "offering_net_weight_kg": item.get("offering_net_weight_kg"),
                }
                for item in repository.list_internal_credit_note_available_items(int(profile["id"]))
            ]}
            catalog = catalog_with_invoice_history(catalog, history_invoice, order)
            snapshot = generate_invoice_document(order, profile, catalog)
            credit_note_id = repository.save_invoice(
                order,
                profile,
                snapshot,
                update_customer=False,
                split_kind="internal",
                fiscal_status="internal",
                document_type="NOTA_CREDITO",
                related_invoice_id=None,
                credit_reason=" / ".join(order.get("notes") or []) or "Nota de crédito interna",
            )
            repository.save_credit_note_item_sources(credit_note_id, source_links)
            return InvoiceCreateOut.model_validate({
                "invoice_id": credit_note_id,
                "invoices": [{"invoice_id": credit_note_id, "split_kind": "internal", "fiscal_status": "internal"}],
                "summary": snapshot["summary"],
            })

        if billing_mode == "internal_only":
            order["declared"] = False
            order["price_list_id"] = order.get("internal_price_list_id") or order.get("price_list_id")
            catalog = repository.get_catalog_for_price_list(int(order["price_list_id"])) if order.get("price_list_id") else repository.get_active_catalog()
            snapshot = generate_invoice_document(order, profile, catalog)
            invoice_id = repository.save_invoice(order, profile, snapshot, update_customer=role == "admin", split_kind="internal", fiscal_status="internal")
            return InvoiceCreateOut.model_validate({
                "invoice_id": invoice_id,
                "invoices": [{"invoice_id": invoice_id, "split_kind": "internal", "fiscal_status": "internal"}],
                "summary": snapshot["summary"],
            })

        if billing_mode == "fiscal_only":
            order["declared"] = True
            order["price_list_id"] = order.get("fiscal_price_list_id") or order.get("price_list_id")
            order["items"] = [{**item, "bonus_quantity": 0} for item in order.get("items", [])]
            profile = profile_with_arca_taxpayer_data(profile)
            catalog = repository.get_catalog_for_price_list(int(order["price_list_id"])) if order.get("price_list_id") else repository.get_active_catalog()
            snapshot = generate_invoice_document(order, profile, catalog)
            snapshot = fiscalize_snapshot(snapshot, catalog)
            invoice_id = repository.save_invoice(order, profile, snapshot, update_customer=role == "admin", split_kind="fiscal", fiscal_status="draft")
            return InvoiceCreateOut.model_validate({
                "invoice_id": invoice_id,
                "invoices": [{"invoice_id": invoice_id, "split_kind": "fiscal", "fiscal_status": "draft"}],
                "summary": snapshot["summary"],
            })

        return build_and_save_split(repository, order, profile, update_customer=role == "admin")
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/{invoice_id}/credit-notes", response_model=InvoiceCreateOut)
def create_credit_note(invoice_id: int, payload: CreditNoteRequest, _: str = Depends(require_admin)) -> InvoiceCreateOut:
    repository = get_repository()
    invoice = repository.get_invoice_detail(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    if is_credit_note(invoice):
        raise HTTPException(status_code=400, detail="No se puede emitir una nota de crédito sobre otra nota de crédito")
    if is_fiscal_invoice(invoice) and str(invoice.get("fiscal_status") or "") != "authorized":
        raise HTTPException(status_code=400, detail="La factura fiscal debe estar autorizada para emitir una nota de crédito")
    try:
        order, iva_by_key = build_credit_note_order(invoice, payload, repository.credited_quantities_for_invoice(invoice_id))
        profile = profile_from_invoice(invoice)
        catalog = repository.get_catalog_for_price_list(int(order["price_list_id"])) if order.get("price_list_id") else repository.get_active_catalog()
        catalog = catalog_with_invoice_history(catalog, invoice, order)
        snapshot = generate_invoice_document(order, profile, catalog) if order.get("items") else empty_credit_note_snapshot(order, profile)
        append_manual_credit_note_item(snapshot, payload.manual_item, fiscal=is_fiscal_invoice(invoice))
        if is_fiscal_invoice(invoice):
            for row in snapshot.get("rows", []):
                if row.get("product_id") is None and row.get("iva_rate") is not None:
                    continue
                key = (str(row.get("product_id") or ""), str(row.get("offering_id") or ""))
                iva_rate = iva_by_key.get(key)
                if iva_rate is None:
                    raise ValueError(f"Falta IVA fiscal para {row.get('label')}")
                row["iva_rate"] = iva_rate
        credit_note_id = repository.save_invoice(
            order,
            profile,
            snapshot,
            update_customer=False,
            split_kind="fiscal" if is_fiscal_invoice(invoice) else "internal",
            fiscal_status="draft" if is_fiscal_invoice(invoice) else "internal",
            document_type="NOTA_CREDITO",
            related_invoice_id=invoice_id,
            credit_reason=payload.reason,
        )
        if not is_fiscal_invoice(invoice) and payload.items:
            items_by_id = {int(source_item["id"]): source_item for source_item in invoice.get("items", [])}
            repository.save_credit_note_item_sources(
                credit_note_id,
                [
                    {
                        "source_invoice_id": invoice_id,
                        "source_invoice_item_id": item.invoice_item_id,
                        "product_id": items_by_id[item.invoice_item_id]["product_id"],
                        "offering_id": items_by_id[item.invoice_item_id]["offering_id"],
                        "unit_price": items_by_id[item.invoice_item_id]["unit_price"],
                        "quantity": item.quantity,
                    }
                    for item in payload.items
                ],
            )
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return InvoiceCreateOut.model_validate({
        "invoice_id": credit_note_id,
        "invoices": [{"invoice_id": credit_note_id, "split_kind": "fiscal" if is_fiscal_invoice(invoice) else "internal", "fiscal_status": "draft" if is_fiscal_invoice(invoice) else "internal"}],
        "summary": snapshot["summary"],
    })


@router.post("/{invoice_id}/arca/authorize", response_model=ArcaAuthorizationOut)
def authorize_invoice_in_arca(invoice_id: int, payload: AuthorizationPayload, _: str = Depends(require_admin)) -> ArcaAuthorizationOut:
    validate_invoice_authorization_password(payload.password)
    repository = get_repository()
    invoice = repository.get_invoice_detail(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    try:
        return ArcaAuthorizationOut.model_validate(authorize_invoice_service(repository, invoice_id))
    except ArcaAuthorizationConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except (ArcaDisabledError, ArcaNotConfiguredError) as error:
        raise HTTPException(status_code=400, detail=str(error) or "ARCA no configurado") from error
    except (ArcaRejectedError, ArcaTechnicalError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error) or "ARCA rechazo la solicitud") from error


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
    is_internal_credit_note = is_credit_note(invoice) and invoice.get("fiscal_status") == "internal"
    try:
        if is_internal_credit_note:
            order, source_links = build_internal_credit_note_from_sources(repository, order, profile, credit_note_invoice_id=invoice_id)
            order["price_list_id"] = order.get("internal_price_list_id") or order.get("price_list_id")
            catalog = repository.get_catalog_for_price_list(int(order["price_list_id"])) if order.get("price_list_id") else repository.get_active_catalog()
            history_invoice = {"items": [
                {
                    "product_id": item["product_id"],
                    "offering_id": item["offering_id"],
                    "product_name": item.get("product_name") or item.get("label"),
                    "offering_label": item.get("offering_label"),
                    "unit_price": item.get("unit_price"),
                    "offering_net_weight_kg": item.get("offering_net_weight_kg"),
                }
                for item in repository.list_internal_credit_note_available_items(int(profile["id"]), credit_note_invoice_id=invoice_id)
            ]}
            catalog = catalog_with_invoice_history(catalog, history_invoice, order)
            snapshot = generate_invoice_document(order, profile, catalog)
            credit_reason = " / ".join(order.get("notes") or []) or "Nota de crédito interna"
            repository.update_invoice(invoice_id, order, profile, snapshot, credit_reason=credit_reason, credit_note_sources=source_links)
            return InvoiceCreateOut.model_validate({
                "invoice_id": invoice_id,
                "invoices": [{"invoice_id": invoice_id, "split_kind": "internal", "fiscal_status": "internal"}],
                "summary": snapshot["summary"],
            })
        if str(order.get("billing_mode") or "") == "fiscal_only" or (bool(order.get("declared")) and batch_id is None):
            profile = profile_with_arca_taxpayer_data(profile)
        if batch_id is not None:
            if str(order.get("billing_mode") or "") != "split":
                raise ValueError("Para editar un batch split se debe regenerar el split completo")
            return build_and_save_split(repository, order, profile, update_customer=True, replace_batch_id=batch_id)

        base_catalog = repository.get_catalog_for_price_list(int(order["price_list_id"])) if order.get("price_list_id") else repository.get_active_catalog()
        catalog = catalog_with_invoice_history(base_catalog, invoice, order)
        snapshot = generate_invoice_document(order, profile, catalog)
        repository.update_invoice(invoice_id, order, profile, snapshot)
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return InvoiceCreateOut.model_validate({
        "invoice_id": invoice_id,
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

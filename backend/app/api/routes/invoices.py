from __future__ import annotations

from datetime import date, timedelta

import os

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response

from ...core.security import AuthManager
from ...dependencies import current_role, get_repository, require_admin
from ...schemas import ArcaAuthorizeRequest, ArcaStatusOut, InvoiceCreateOut, InvoiceDetailOut, InvoiceListItemOut, InvoiceRequest, StatusResponse
from ...services.arca.config import load_arca_config
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


def order_fiscal_kind(order: dict) -> str:
    fiscal_kind = str(order.get("fiscal_kind") or "").strip().lower()
    if fiscal_kind in {"internal", "fiscal"}:
        return fiscal_kind
    return "fiscal" if bool(order.get("declared", False)) else "internal"


def verify_sensitive_invoice_password(password: str) -> None:
    password_hash = os.getenv("GRANALIA_INVOICE_AUTH_PASSWORD_HASH")
    plain_password = os.getenv("GRANALIA_INVOICE_AUTH_PASSWORD")
    if not password_hash and plain_password:
        if password == plain_password:
            return
        raise HTTPException(status_code=403, detail="Contraseña de autorización inválida")
    if not password_hash:
        raise HTTPException(status_code=503, detail="Contraseña de autorización no configurada")
    if not AuthManager.verify_password(password, password_hash):
        raise HTTPException(status_code=403, detail="Contraseña de autorización inválida")


def arca_environment() -> str:
    return load_arca_config().environment


def arca_is_configured() -> bool:
    return load_arca_config().configured


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
    if order_fiscal_kind(order) == "fiscal" and role != "admin":
        raise HTTPException(status_code=403, detail="Solo administradores pueden crear facturas fiscales")
    try:
        catalog = repository.get_catalog_for_price_list(int(order["price_list_id"])) if order.get("price_list_id") else repository.get_active_catalog()
        filename, xlsx_bytes, snapshot = generate_invoice_document(order, profile, catalog)
        invoice_id = repository.save_invoice(order, profile, snapshot, filename, xlsx_bytes, update_customer=role == "admin")
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return InvoiceCreateOut.model_validate({
        "invoice_id": invoice_id,
        "filename": filename,
        "download_url": f"/api/invoices/{invoice_id}/xlsx",
        "summary": snapshot["summary"],
    })


@router.put("/{invoice_id}", response_model=InvoiceCreateOut)
def update_invoice(invoice_id: int, payload: InvoiceRequest, _: str = Depends(require_admin)) -> InvoiceCreateOut:
    repository = get_repository()
    invoice = repository.get_invoice_detail(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    order = payload.order.model_dump()
    profile = payload.profile.model_dump()
    try:
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
    if not repository.get_invoice_detail(invoice_id):
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    try:
        repository.delete_invoice(invoice_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return StatusResponse(status="deleted")


@router.get("/{invoice_id}/arca/status", response_model=ArcaStatusOut)
def arca_status(invoice_id: int, _: str = Depends(require_admin)) -> ArcaStatusOut:
    invoice = get_repository().get_invoice_detail(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    configured = arca_is_configured()
    return ArcaStatusOut(
        configured=configured,
        environment=arca_environment(),
        fiscal_kind=str(invoice.get("fiscal_kind") or "internal"),
        fiscal_status=str(invoice.get("fiscal_status") or "draft"),
        message="ARCA configurado" if configured else "ARCA no configurado",
    )


@router.post("/{invoice_id}/arca/authorize", response_model=ArcaStatusOut)
def authorize_invoice_in_arca(invoice_id: int, payload: ArcaAuthorizeRequest, _: str = Depends(require_admin)) -> ArcaStatusOut:
    verify_sensitive_invoice_password(payload.password)
    invoice = get_repository().get_invoice_detail(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    if str(invoice.get("fiscal_kind") or "internal") != "fiscal":
        raise HTTPException(status_code=400, detail="Solo facturas fiscales pueden autorizarse en ARCA")
    fiscal_status = str(invoice.get("fiscal_status") or "draft")
    if fiscal_status == "authorized":
        raise HTTPException(status_code=409, detail="La factura ya está autorizada por ARCA")
    if fiscal_status not in {"draft", "rejected"}:
        raise HTTPException(status_code=400, detail="La factura no está en un estado autorizable")
    if not arca_is_configured():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="ARCA no configurado")
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Cliente WSAA/WSFEv1 pendiente de homologación")

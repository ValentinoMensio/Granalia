from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from ...dependencies import get_repository
from ...schemas import InvoiceCreateOut, InvoiceDetailOut, InvoiceListItemOut, InvoiceRequest, StatusResponse
from ...services.pdf import build_invoice_pdf
from ...services.invoicing import generate_invoice_document


router = APIRouter(prefix="/api/invoices", tags=["invoices"])


@router.get("", response_model=list[InvoiceListItemOut])
def invoices(limit: int = 50) -> list[InvoiceListItemOut]:
    return [InvoiceListItemOut.model_validate(item) for item in get_repository().list_invoices(limit=limit)]


@router.get("/{invoice_id}", response_model=InvoiceDetailOut)
def invoice_detail(invoice_id: int) -> InvoiceDetailOut:
    invoice = get_repository().get_invoice_detail(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    return InvoiceDetailOut.model_validate(invoice)


@router.get("/{invoice_id}/xlsx")
def download_invoice(invoice_id: int) -> Response:
    invoice = get_repository().get_invoice_file(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    return Response(
        content=invoice["xlsx_data"],
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{invoice["output_filename"]}"'},
    )


@router.get("/{invoice_id}/pdf")
def download_invoice_pdf(invoice_id: int) -> Response:
    invoice = get_repository().get_invoice_detail(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    pdf_bytes = build_invoice_pdf(invoice)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="factura-{invoice_id}.pdf"'},
    )


@router.post("", response_model=InvoiceCreateOut)
def create_invoice(payload: InvoiceRequest) -> InvoiceCreateOut:
    repository = get_repository()
    order = payload.order.model_dump()
    profile = payload.profile.model_dump()
    catalog = repository.get_active_catalog()
    filename, xlsx_bytes, snapshot = generate_invoice_document(order, profile, catalog)
    invoice_id = repository.save_invoice(order, profile, snapshot, filename, xlsx_bytes)
    return InvoiceCreateOut.model_validate({
        "invoice_id": invoice_id,
        "filename": filename,
        "download_url": f"/api/invoices/{invoice_id}/xlsx",
        "summary": snapshot["summary"],
    })


@router.put("/{invoice_id}", response_model=InvoiceCreateOut)
def update_invoice(invoice_id: int, payload: InvoiceRequest) -> InvoiceCreateOut:
    repository = get_repository()
    if not repository.get_invoice_detail(invoice_id):
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    order = payload.order.model_dump()
    profile = payload.profile.model_dump()
    catalog = repository.get_active_catalog()
    filename, xlsx_bytes, snapshot = generate_invoice_document(order, profile, catalog)
    repository.update_invoice(invoice_id, order, profile, snapshot, filename, xlsx_bytes)
    return InvoiceCreateOut.model_validate({
        "invoice_id": invoice_id,
        "filename": filename,
        "download_url": f"/api/invoices/{invoice_id}/xlsx",
        "summary": snapshot["summary"],
    })


@router.delete("/{invoice_id}", response_model=StatusResponse)
def delete_invoice(invoice_id: int) -> StatusResponse:
    repository = get_repository()
    if not repository.get_invoice_detail(invoice_id):
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    repository.delete_invoice(invoice_id)
    return StatusResponse(status="deleted")

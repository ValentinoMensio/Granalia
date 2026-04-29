from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ...dependencies import get_repository
from ...schemas import MAX_NAME_LENGTH, PriceListMetaOut, PriceListUploadOut, ProductCatalogOut, StatusResponse
from ...services.catalog import build_catalog_snapshot_from_pdf


router = APIRouter(prefix="/api/price-lists", tags=["price-lists"])
MAX_PRICE_LIST_PDF_BYTES = 20 * 1024 * 1024


@router.post("/upload")
async def upload_price_list(file: UploadFile = File(...), name: str = Form(default=""), activate: bool = Form(default=True), price_list_id: int | None = Form(default=None)) -> PriceListUploadOut:
    if file.content_type not in {"application/pdf", "application/octet-stream"}:
        raise HTTPException(status_code=400, detail="El archivo debe ser PDF")
    filename = file.filename or "lista.pdf"
    if len(filename) > MAX_NAME_LENGTH:
        raise HTTPException(status_code=400, detail=f"El nombre del archivo no puede superar {MAX_NAME_LENGTH} caracteres")
    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="El PDF está vacío")
    if len(pdf_bytes) > MAX_PRICE_LIST_PDF_BYTES:
        raise HTTPException(status_code=413, detail="El PDF no puede superar 20 MB")
    repository = get_repository()
    list_name = name.strip() or filename
    price_list = repository.save_price_list(filename, pdf_bytes, activate=activate, source="upload", name=list_name if price_list_id is None else None, price_list_id=price_list_id)
    base_catalog = repository.get_catalog_for_price_list(price_list_id) if price_list_id is not None else repository.get_active_catalog()
    updated_catalog = build_catalog_snapshot_from_pdf(pdf_bytes, base_catalog)
    repository.replace_active_catalog(updated_catalog, name=f"Catalogo desde {list_name}", price_list_id=int(price_list["id"]), active=activate)
    return PriceListUploadOut.model_validate({"bootstrap": repository.bootstrap_payload()})


@router.get("", response_model=list[PriceListMetaOut])
def list_price_lists() -> list[PriceListMetaOut]:
    return [PriceListMetaOut.model_validate(item) for item in get_repository().list_price_lists()]


@router.get("/{price_list_id}/catalog", response_model=list[ProductCatalogOut])
def price_list_catalog(price_list_id: int) -> list[ProductCatalogOut]:
    try:
        catalog = get_repository().get_catalog_for_price_list(price_list_id)
    except RuntimeError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return [ProductCatalogOut.model_validate(item) for item in catalog]


@router.delete("/{price_list_id}", response_model=StatusResponse)
def delete_price_list(price_list_id: int) -> StatusResponse:
    try:
        get_repository().delete_price_list(price_list_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return StatusResponse(status="deleted")

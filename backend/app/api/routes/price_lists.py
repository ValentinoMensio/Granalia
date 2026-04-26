from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from ...dependencies import get_repository
from ...schemas import MAX_NAME_LENGTH, PriceListUploadOut
from ...services.catalog import build_catalog_snapshot_from_pdf


router = APIRouter(prefix="/api/price-lists", tags=["price-lists"])
MAX_PRICE_LIST_PDF_BYTES = 20 * 1024 * 1024


@router.post("/upload")
async def upload_price_list(file: UploadFile = File(...)) -> PriceListUploadOut:
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
    repository.save_price_list(filename, pdf_bytes, activate=True, source="upload")
    updated_catalog = build_catalog_snapshot_from_pdf(pdf_bytes, repository.get_active_catalog())
    repository.replace_active_catalog(updated_catalog, name=f"Catalogo desde {filename}")
    return PriceListUploadOut.model_validate({"bootstrap": repository.bootstrap_payload()})

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from ...dependencies import get_repository
from ...schemas import PriceListUploadOut
from ...services.catalog import build_catalog_snapshot_from_pdf


router = APIRouter(prefix="/api/price-lists", tags=["price-lists"])


@router.post("/upload")
async def upload_price_list(file: UploadFile = File(...)) -> PriceListUploadOut:
    if file.content_type not in {"application/pdf", "application/octet-stream"}:
        raise HTTPException(status_code=400, detail="El archivo debe ser PDF")
    pdf_bytes = await file.read()
    repository = get_repository()
    repository.save_price_list(file.filename or "lista.pdf", pdf_bytes, activate=True, source="upload")
    updated_catalog = build_catalog_snapshot_from_pdf(pdf_bytes, repository.get_active_catalog())
    repository.replace_active_catalog(updated_catalog, name=f"Catalogo desde {file.filename or 'lista.pdf'}")
    return PriceListUploadOut.model_validate({"bootstrap": repository.bootstrap_payload()})

from __future__ import annotations

from io import BytesIO

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pypdf import PdfReader

from ...dependencies import get_repository, require_admin
from ...schemas import MAX_NAME_LENGTH, PriceListCommit, PriceListMetaOut, PriceListPreviewOut, PriceListProductUpdate, PriceListRename, PriceListUploadOut, PriceListVersionOut, ProductCatalogOut, StatusResponse
from ...services.catalog import build_catalog_preview_snapshot_from_pdf, build_catalog_snapshot_from_pdf, ensure_catalog_snapshot_x1kg


router = APIRouter(prefix="/api/price-lists", tags=["price-lists"])
MAX_PRICE_LIST_PDF_BYTES = 20 * 1024 * 1024
MAX_PRICE_LIST_PDF_PAGES = 20


def _validate_pdf_upload(file: UploadFile, pdf_bytes: bytes) -> None:
    filename = file.filename or "lista.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="El archivo debe tener extensión .pdf")
    if file.content_type not in {"application/pdf", "application/octet-stream"}:
        raise HTTPException(status_code=400, detail="El archivo debe ser PDF")
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="El PDF está vacío")
    if len(pdf_bytes) > MAX_PRICE_LIST_PDF_BYTES:
        raise HTTPException(status_code=413, detail="El PDF no puede superar 20 MB")
    if not pdf_bytes.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="El contenido no parece ser un PDF válido")
    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        if reader.is_encrypted:
            raise HTTPException(status_code=400, detail="El PDF no puede estar cifrado")
        if len(reader.pages) > MAX_PRICE_LIST_PDF_PAGES:
            raise HTTPException(status_code=413, detail=f"El PDF no puede superar {MAX_PRICE_LIST_PDF_PAGES} páginas")
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=400, detail="No se pudo leer el PDF") from error


def _catalog_payload(catalog: list[object]) -> list[dict[str, object]]:
    return [
        {
            "id": product.id,
            "name": product.name,
            "aliases": list(product.aliases),
            "iva_rate": product.iva_rate,
            "offerings": [offering.model_dump() for offering in product.offerings],
        }
        for product in catalog
    ]


@router.post("/upload")
async def upload_price_list(file: UploadFile = File(...), name: str = Form(default=""), activate: bool = Form(default=True), price_list_id: int | None = Form(default=None), _: str = Depends(require_admin)) -> PriceListUploadOut:
    filename = file.filename or "lista.pdf"
    if len(filename) > MAX_NAME_LENGTH:
        raise HTTPException(status_code=400, detail=f"El nombre del archivo no puede superar {MAX_NAME_LENGTH} caracteres")
    pdf_bytes = await file.read()
    _validate_pdf_upload(file, pdf_bytes)
    repository = get_repository()
    list_name = name.strip() or (None if price_list_id is not None else filename)
    try:
        base_catalog = repository.get_catalog_for_price_list(price_list_id) if price_list_id is not None else repository.get_active_catalog()
        updated_catalog = build_catalog_snapshot_from_pdf(pdf_bytes, base_catalog)
        repository.save_price_list_with_catalog(
            filename=filename,
            pdf_bytes=pdf_bytes,
            catalog=updated_catalog,
            activate=activate,
            source="upload",
            name=list_name,
            price_list_id=price_list_id,
        )
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return PriceListUploadOut.model_validate({"bootstrap": repository.bootstrap_payload()})


@router.post("/preview", response_model=PriceListPreviewOut)
async def preview_price_list(file: UploadFile = File(...), price_list_id: int | None = Form(default=None), _: str = Depends(require_admin)) -> PriceListPreviewOut:
    filename = file.filename or "lista.pdf"
    if len(filename) > MAX_NAME_LENGTH:
        raise HTTPException(status_code=400, detail=f"El nombre del archivo no puede superar {MAX_NAME_LENGTH} caracteres")
    pdf_bytes = await file.read()
    _validate_pdf_upload(file, pdf_bytes)
    repository = get_repository()
    try:
        base_catalog = repository.get_catalog_for_price_list(price_list_id) if price_list_id is not None else repository.get_active_catalog()
        preview = build_catalog_preview_snapshot_from_pdf(pdf_bytes, base_catalog)
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return PriceListPreviewOut.model_validate(preview)


@router.post("/commit", response_model=PriceListUploadOut)
def commit_price_list(payload: PriceListCommit, _: str = Depends(require_admin)) -> PriceListUploadOut:
    if not payload.catalog:
        raise HTTPException(status_code=400, detail="La lista debe incluir al menos un producto")
    repository = get_repository()
    list_name = payload.name.strip() or (None if payload.price_list_id is not None else "Lista manual")
    filename = payload.filename.strip() or "lista-manual.pdf"
    try:
        repository.save_price_list_with_catalog(
            filename=filename,
            pdf_bytes=b"",
            catalog=ensure_catalog_snapshot_x1kg(_catalog_payload(payload.catalog)),
            activate=payload.activate,
            source=payload.source or "manual",
            name=list_name,
            price_list_id=payload.price_list_id,
        )
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return PriceListUploadOut.model_validate({"bootstrap": repository.bootstrap_payload()})


@router.get("", response_model=list[PriceListMetaOut])
def list_price_lists(_: str = Depends(require_admin)) -> list[PriceListMetaOut]:
    return [PriceListMetaOut.model_validate(item) for item in get_repository().list_price_lists()]


@router.get("/versions", response_model=list[PriceListVersionOut])
def list_price_list_versions(_: str = Depends(require_admin)) -> list[PriceListVersionOut]:
    return [PriceListVersionOut.model_validate(item) for item in get_repository().list_price_list_versions()]


@router.patch("/{price_list_id}", response_model=StatusResponse)
def rename_price_list(price_list_id: int, payload: PriceListRename, _: str = Depends(require_admin)) -> StatusResponse:
    try:
        get_repository().rename_price_list(price_list_id, payload.name)
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return StatusResponse(status="updated")


@router.post("/{price_list_id}/activate", response_model=StatusResponse)
def activate_price_list(price_list_id: int, _: str = Depends(require_admin)) -> StatusResponse:
    try:
        get_repository().activate_price_list(price_list_id)
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return StatusResponse(status="activated")


@router.get("/{price_list_id}/catalog", response_model=list[ProductCatalogOut])
def price_list_catalog(price_list_id: int) -> list[ProductCatalogOut]:
    try:
        catalog = get_repository().get_catalog_for_price_list(price_list_id)
    except RuntimeError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return [ProductCatalogOut.model_validate(item) for item in catalog]


@router.put("/{price_list_id}/products", response_model=ProductCatalogOut)
def update_price_list_product(price_list_id: int, payload: PriceListProductUpdate, _: str = Depends(require_admin)) -> ProductCatalogOut:
    try:
        product = get_repository().update_price_list_product(
            price_list_id,
            payload.product.model_dump(),
            [offering.model_dump() for offering in payload.offerings],
        )
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return ProductCatalogOut.model_validate(product)


@router.delete("/{price_list_id}", response_model=StatusResponse)
def delete_price_list(price_list_id: int, _: str = Depends(require_admin)) -> StatusResponse:
    try:
        get_repository().delete_price_list(price_list_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return StatusResponse(status="deleted")

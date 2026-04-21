from __future__ import annotations

from fastapi import APIRouter

from ...dependencies import get_repository
from ...schemas import (
    ProductCatalogOut,
    ProductOfferingUpsert,
    ProductOut,
    ProductUpsert,
    StatusResponse,
    TransportOut,
    TransportUpsert,
)

router = APIRouter(tags=["lookups"])


@router.get("/api/transports", response_model=list[TransportOut])
def transports() -> list[TransportOut]:
    return get_repository().get_transports()


@router.post("/api/transports", response_model=TransportOut)
def create_transport(payload: TransportUpsert) -> TransportOut:
    return get_repository().save_transport(
        name=payload.name,
        notes=payload.notes,
    )


@router.put("/api/transports/{transport_id}", response_model=TransportOut)
def update_transport(transport_id: int, payload: TransportUpsert) -> TransportOut:
    return get_repository().save_transport(
        name=payload.name,
        notes=payload.notes,
        transport_id=transport_id,
    )


@router.delete("/api/transports/{transport_id}", response_model=StatusResponse)
def delete_transport(transport_id: int) -> StatusResponse:
    get_repository().delete_transport(transport_id)
    return {"status": "deleted"}


@router.get("/api/products", response_model=list[ProductCatalogOut])
def products() -> list[ProductCatalogOut]:
    return get_repository().get_active_catalog()


@router.post("/api/products", response_model=ProductOut)
def upsert_product(payload: ProductUpsert) -> ProductOut:
    return get_repository().save_product(payload.model_dump())


@router.post("/api/products/{product_id}/offerings", response_model=StatusResponse)
def update_product_offerings(product_id: int, payload: list[ProductOfferingUpsert]) -> StatusResponse:
    get_repository().save_product_offerings(
        product_id,
        [offering.model_dump() for offering in payload],
    )
    return {"status": "offerings updated"}


@router.delete("/api/products/{product_id}", response_model=StatusResponse)
def delete_product(product_id: int) -> StatusResponse:
    get_repository().delete_product(product_id)
    return {"status": "deleted"}

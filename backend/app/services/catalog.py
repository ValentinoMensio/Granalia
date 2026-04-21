from __future__ import annotations

from ..domain.models import CatalogProduct
from ..types import CatalogProductData
from .price_list_parser import build_catalog_from_pdf


def build_catalog_snapshot_from_pdf(pdf_bytes: bytes, current_catalog: list[CatalogProductData]) -> list[CatalogProductData]:
    models = [CatalogProduct.from_data(item) for item in current_catalog]
    return [item.to_data() for item in build_catalog_from_pdf(pdf_bytes, models)]

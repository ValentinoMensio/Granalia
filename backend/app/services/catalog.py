from __future__ import annotations

from ..domain.models import CatalogProduct
from ..types import CatalogProductData
from .price_list_parser import build_catalog_from_pdf, build_catalog_preview_from_pdf


def build_catalog_snapshot_from_pdf(pdf_bytes: bytes, current_catalog: list[CatalogProductData]) -> list[CatalogProductData]:
    models = [CatalogProduct.from_data(item) for item in current_catalog]
    return [item.to_data() for item in build_catalog_from_pdf(pdf_bytes, models)]


def build_catalog_preview_snapshot_from_pdf(pdf_bytes: bytes, current_catalog: list[CatalogProductData]) -> dict[str, object]:
    models = [CatalogProduct.from_data(item) for item in current_catalog]
    result = build_catalog_preview_from_pdf(pdf_bytes, models)
    return {"catalog": [item.to_data() for item in result["catalog"]], "warnings": result["warnings"]}


def ensure_catalog_snapshot_x1kg(catalog: list[CatalogProductData]) -> list[CatalogProductData]:
    result: list[CatalogProductData] = []
    for product in catalog:
        offerings = [dict(offering) for offering in product.get("offerings", [])]
        if any(str(offering.get("label") or "").strip().lower() in {"x 1 kg", "x1 kg", "x1kg"} for offering in offerings):
            result.append({**product, "offerings": offerings})
            continue
        source = next((offering for offering in offerings if int(offering.get("price") or 0) > 0 and float(offering.get("net_weight_kg") or 0) > 0), None)
        if source:
            offerings.append({"id": "x1kg", "label": "x 1 kg", "price": round(int(source.get("price") or 0) / float(source.get("net_weight_kg") or 1)), "net_weight_kg": 1})
        result.append({**product, "offerings": offerings})
    return result

from __future__ import annotations

from ..domain.models import CatalogProduct, CustomerProfile, InvoiceSnapshot, Order
from ..dependencies import BASE_DIR
from ..types import CatalogProductData, CustomerProfileData, InvoiceSnapshotData, OrderData
from .xlsx import build_invoice_snapshot, export_order


def generate_invoice_document(
    order: OrderData,
    profile: CustomerProfileData,
    catalog: list[CatalogProductData],
) -> tuple[str, bytes, InvoiceSnapshotData]:
    order_model = Order.from_data(order)
    profile_model = CustomerProfile.from_data(profile)
    catalog_models = [CatalogProduct.from_data(item) for item in catalog]
    filename, xlsx_bytes = export_order(BASE_DIR, order_model, profile_model, catalog_models)
    snapshot = build_invoice_snapshot(order_model, profile_model, catalog_models)
    return filename, xlsx_bytes, snapshot.to_data()

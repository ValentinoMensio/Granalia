from __future__ import annotations

from ..domain.models import CatalogProduct, CustomerProfile, Order
from ..types import CatalogProductData, CustomerProfileData, InvoiceSnapshotData, OrderData
from .snapshot import build_invoice_snapshot


def generate_invoice_document(
    order: OrderData,
    profile: CustomerProfileData,
    catalog: list[CatalogProductData],
) -> InvoiceSnapshotData:
    order_model = Order.from_data(order)
    profile_model = CustomerProfile.from_data(profile)
    catalog_models = [CatalogProduct.from_data(item) for item in catalog]
    snapshot = build_invoice_snapshot(order_model, profile_model, catalog_models)
    return snapshot.to_data()

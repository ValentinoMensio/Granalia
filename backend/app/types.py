from __future__ import annotations

from datetime import datetime
from typing import NotRequired, TypedDict


class FooterDiscountData(TypedDict):
    label: str
    rate: float


class AutomaticBonusRuleData(TypedDict):
    product_id: int | None
    offering_id: int | None
    offering_label: NotRequired[str]
    buy_quantity: int
    bonus_quantity: int


class CatalogOfferingData(TypedDict):
    id: int | str
    label: str
    price: int
    net_weight_kg: NotRequired[float]
    format_class: NotRequired[str]


class CatalogProductData(TypedDict):
    id: int | str
    name: str
    aliases: list[str]
    offerings: list[CatalogOfferingData]
    active: NotRequired[bool]
    created_at: NotRequired[str | datetime]
    updated_at: NotRequired[str | datetime]


class TransportData(TypedDict):
    transport_id: int
    name: str
    notes: list[str]
    created_at: str | datetime
    updated_at: str | datetime


class CustomerProfileData(TypedDict):
    name: str
    cuit: str
    address: str
    business_name: str
    email: str
    secondary_line: str
    transport: str
    notes: list[str]
    footer_discounts: list[FooterDiscountData]
    line_discounts_by_format: dict[str, float]
    automatic_bonus_rules: list[AutomaticBonusRuleData]
    automatic_bonus_disables_line_discount: bool
    source_count: int
    id: NotRequired[int]
    transport_id: NotRequired[int | None]
    created_at: NotRequired[str | datetime]
    updated_at: NotRequired[str | datetime]


class OrderItemData(TypedDict):
    product_id: int
    offering_id: int
    quantity: float
    bonus_quantity: int
    unit_price: NotRequired[int]


class OrderData(TypedDict):
    client_name: str
    date: str
    price_list_id: NotRequired[int | None]
    declared: NotRequired[bool]
    secondary_line: str
    transport: str
    notes: list[str]
    items: list[OrderItemData]


class InvoiceRowData(TypedDict):
    product_id: int | None
    offering_id: int | None
    label: str
    quantity: float
    unit_price: int
    gross: int
    discount: int
    total: int


class InvoiceSummaryData(TypedDict):
    gross_total: int
    discount_total: int
    final_total: int
    total_bultos: float


class InvoiceSnapshotData(TypedDict):
    rows: list[InvoiceRowData]
    summary: InvoiceSummaryData
    order: OrderData
    profile: CustomerProfileData


class InvoiceListItemData(TypedDict):
    invoice_id: int
    customer_id: int | None
    transport_id: int | None
    client_name: str
    transport: str
    order_date: str
    price_list_id: int | None
    price_list_name: str
    declared: bool
    total_bultos: float
    gross_total: int
    discount_total: int
    final_total: int
    output_filename: str
    xlsx_size: int
    created_at: str | datetime


class InvoiceItemDetailData(TypedDict):
    id: int
    invoice_id: int
    line_number: int
    product_id: int | None
    offering_id: int | None
    label: str
    quantity: float
    unit_price: int
    gross: int
    discount: int
    total: int
    product_name: str | None
    offering_label: str | None
    offering_net_weight_kg: NotRequired[float]


class InvoiceDetailData(TypedDict):
    id: int
    customer_id: int | None
    transport_id: int | None
    legacy_key: str | None
    client_name: str
    order_date: str
    price_list_id: int | None
    price_list_name: str
    declared: bool
    secondary_line: str
    transport: str
    notes: list[str]
    footer_discounts: list[FooterDiscountData]
    line_discounts_by_format: dict[str, float]
    total_bultos: float
    gross_total: int
    discount_total: int
    final_total: int
    output_filename: str
    xlsx_size: int
    created_at: str | datetime
    customer_name: str | None
    customer_cuit: str | None
    customer_address: str | None
    customer_email: str | None
    transport_name: str | None
    items: list[InvoiceItemDetailData]


class InvoiceFileData(TypedDict):
    output_filename: str
    xlsx_data: bytes
    xlsx_size: int


class PriceListMetaData(TypedDict):
    id: NotRequired[int]
    name: str
    filename: str
    content_type: str
    size: int
    active: bool
    source: str
    uploaded_at: str | datetime
    updated_at: str | datetime


class DatabaseInfoData(TypedDict):
    type: str
    url: str


class BootstrapPayloadData(TypedDict):
    catalog: list[CatalogProductData]
    profiles: dict[str, CustomerProfileData]
    clients: list[str]
    transports: list[TransportData]
    price_lists: list[PriceListMetaData]
    price_list: PriceListMetaData | None
    database: DatabaseInfoData

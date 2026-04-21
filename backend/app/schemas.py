from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, Field, field_validator


NonEmptyStr = Annotated[str, Field(min_length=1)]
NonNegativeInt = Annotated[int, Field(ge=0)]


def _strip_required(value: str) -> str:
    text = value.strip()
    if not text:
        raise ValueError("must not be empty")
    return text


def _strip_optional(value: str) -> str:
    return value.strip()


class FooterDiscount(BaseModel):
    label: NonEmptyStr
    rate: float = Field(ge=0, le=1)

    _normalize_label = field_validator("label")(_strip_required)


class InvoiceItemInput(BaseModel):
    product_id: int
    offering_id: int
    quantity: NonNegativeInt
    bonus_quantity: NonNegativeInt = 0


class InvoiceCreate(BaseModel):
    client_name: NonEmptyStr
    date: str
    secondary_line: str = ""
    transport: str = ""
    notes: list[str] = Field(default_factory=list)
    items: list[InvoiceItemInput]

    _normalize_client_name = field_validator("client_name")(_strip_required)
    _normalize_secondary_line = field_validator("secondary_line", "transport")(_strip_optional)

    @field_validator("notes")
    @classmethod
    def normalize_notes(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]


class CustomerUpsert(BaseModel):
    id: int | None = None
    name: NonEmptyStr
    secondary_line: str = ""
    transport: str = ""
    notes: list[str] = Field(default_factory=list)
    footer_discounts: list[FooterDiscount] = Field(default_factory=list)
    line_discounts_by_format: dict[str, float] = Field(default_factory=dict)
    source_count: NonNegativeInt = 0

    _normalize_name = field_validator("name")(_strip_required)
    _normalize_secondary_line = field_validator("secondary_line", "transport")(_strip_optional)

    @field_validator("notes")
    @classmethod
    def normalize_customer_notes(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]

    @field_validator("line_discounts_by_format")
    @classmethod
    def validate_line_discounts(cls, value: dict[str, float]) -> dict[str, float]:
        normalized: dict[str, float] = {}
        for key, rate in value.items():
            label = key.strip()
            if not label:
                raise ValueError("discount keys must not be empty")
            numeric_rate = float(rate)
            if numeric_rate < 0 or numeric_rate > 1:
                raise ValueError("discount rates must be between 0 and 1")
            normalized[label] = numeric_rate
        return normalized


class InvoiceRequest(BaseModel):
    order: InvoiceCreate
    profile: CustomerUpsert


class TransportUpsert(BaseModel):
    name: NonEmptyStr
    notes: list[str] = Field(default_factory=list)

    _normalize_name = field_validator("name")(_strip_required)

    @field_validator("notes")
    @classmethod
    def normalize_transport_notes(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]


class ProductUpsert(BaseModel):
    id: int | None = None
    name: NonEmptyStr
    aliases: list[str] = Field(default_factory=list)

    _normalize_name = field_validator("name")(_strip_required)

    @field_validator("aliases")
    @classmethod
    def normalize_aliases(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if item.strip()]
        return list(dict.fromkeys(normalized))


class ProductOfferingUpsert(BaseModel):
    id: int | None = None
    label: NonEmptyStr
    price: NonNegativeInt

    _normalize_label = field_validator("label")(_strip_required)


class StatusResponse(BaseModel):
    status: str


class TransportOut(BaseModel):
    transport_id: int
    name: str
    notes: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str


class ProductOfferingOut(BaseModel):
    id: int
    label: str
    price: int


class ProductCatalogOut(BaseModel):
    id: int
    name: str
    aliases: list[str] = Field(default_factory=list)
    offerings: list[ProductOfferingOut] = Field(default_factory=list)


class ProductOut(BaseModel):
    id: int
    name: str
    aliases: list[str] = Field(default_factory=list)
    active: bool
    created_at: str
    updated_at: str


class CustomerOut(BaseModel):
    id: int
    name: str
    secondary_line: str = ""
    transport: str = ""
    notes: list[str] = Field(default_factory=list)
    footer_discounts: list[FooterDiscount] = Field(default_factory=list)
    line_discounts_by_format: dict[str, float] = Field(default_factory=dict)
    source_count: int = 0
    transport_id: int | None = None
    created_at: str
    updated_at: str


class PriceListMetaOut(BaseModel):
    id: int
    filename: str
    content_type: str
    size: int
    active: bool
    source: str
    uploaded_at: str
    updated_at: str


class DatabaseInfoOut(BaseModel):
    type: str
    url: str


class BootstrapOut(BaseModel):
    catalog: list[ProductCatalogOut] = Field(default_factory=list)
    profiles: dict[str, CustomerOut] = Field(default_factory=dict)
    clients: list[str] = Field(default_factory=list)
    transports: list[TransportOut] = Field(default_factory=list)
    price_list: PriceListMetaOut | None = None
    database: DatabaseInfoOut


class CustomerMutationOut(BaseModel):
    customer: CustomerOut
    bootstrap: BootstrapOut


class InvoiceSummaryOut(BaseModel):
    gross_total: int
    discount_total: int
    final_total: int
    total_bultos: int


class InvoiceListItemOut(BaseModel):
    invoice_id: int
    customer_id: int | None = None
    transport_id: int | None = None
    client_name: str
    transport: str = ""
    order_date: str
    total_bultos: int
    gross_total: int
    discount_total: int
    final_total: int
    output_filename: str
    xlsx_size: int
    created_at: str


class InvoiceItemOut(BaseModel):
    id: int
    invoice_id: int
    line_number: int
    product_id: int | None = None
    offering_id: int | None = None
    label: str
    quantity: int
    unit_price: int
    gross: int
    discount: int
    total: int
    product_name: str | None = None
    offering_label: str | None = None


class InvoiceDetailOut(BaseModel):
    id: int
    customer_id: int | None = None
    transport_id: int | None = None
    legacy_key: str | None = None
    client_name: str
    order_date: str
    secondary_line: str = ""
    transport: str = ""
    notes: list[str] = Field(default_factory=list)
    footer_discounts: list[FooterDiscount] = Field(default_factory=list)
    line_discounts_by_format: dict[str, float] = Field(default_factory=dict)
    total_bultos: int
    gross_total: int
    discount_total: int
    final_total: int
    output_filename: str
    xlsx_size: int
    created_at: str
    customer_name: str | None = None
    transport_name: str | None = None
    items: list[InvoiceItemOut] = Field(default_factory=list)


class InvoiceCreateOut(BaseModel):
    invoice_id: int
    filename: str
    download_url: str
    summary: InvoiceSummaryOut


class AuthSessionOut(BaseModel):
    authenticated: bool
    username: str | None = None


class HealthOut(BaseModel):
    status: str


class PriceListUploadOut(BaseModel):
    bootstrap: BootstrapOut

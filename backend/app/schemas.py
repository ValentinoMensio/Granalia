from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, Field, field_validator


MAX_NAME_LENGTH = 255
MAX_SHORT_TEXT_LENGTH = 500
MAX_NOTE_LENGTH = 1000
MAX_NOTES = 30
MAX_INVOICE_ITEMS = 500
MAX_DISCOUNTS = 30
MAX_LINE_DISCOUNT_GROUPS = 100
MAX_AUTOMATIC_BONUS_RULES = 100
MAX_ALIASES = 50
MAX_PRODUCT_OFFERINGS = 100


NonEmptyStr = Annotated[str, Field(min_length=1, max_length=MAX_NAME_LENGTH)]
OfferingLabelStr = Annotated[str, Field(min_length=1, max_length=120)]
NonNegativeInt = Annotated[int, Field(ge=0)]


def _strip_required(value: str) -> str:
    text = value.strip()
    if not text:
        raise ValueError("must not be empty")
    return text


def _strip_optional(value: str) -> str:
    text = value.strip()
    if len(text) > MAX_SHORT_TEXT_LENGTH:
        raise ValueError(f"must be at most {MAX_SHORT_TEXT_LENGTH} characters")
    return text


def _normalize_text_list(value: list[str]) -> list[str]:
    normalized = [item.strip() for item in value if item.strip()]
    for item in normalized:
        if len(item) > MAX_NOTE_LENGTH:
            raise ValueError(f"list entries must be at most {MAX_NOTE_LENGTH} characters")
    return normalized


class FooterDiscount(BaseModel):
    label: NonEmptyStr
    rate: float = Field(ge=0, le=1)

    _normalize_label = field_validator("label")(_strip_required)


class InvoiceItemInput(BaseModel):
    product_id: int
    offering_id: int
    quantity: NonNegativeInt
    bonus_quantity: NonNegativeInt = 0
    unit_price: NonNegativeInt | None = None


class AutomaticBonusRule(BaseModel):
    product_id: int | None = None
    offering_id: int | None = None
    offering_label: str = Field(default="", max_length=120)
    buy_quantity: int = Field(default=10, ge=1, le=10000)
    bonus_quantity: int = Field(default=1, ge=1, le=10000)
    disables_line_discount_when_bonus: bool = False

    _normalize_offering_label = field_validator("offering_label")(_strip_optional)


class InvoiceCreate(BaseModel):
    client_name: NonEmptyStr
    date: str = Field(min_length=10, max_length=10)
    secondary_line: str = Field(default="", max_length=MAX_SHORT_TEXT_LENGTH)
    transport: str = Field(default="", max_length=MAX_SHORT_TEXT_LENGTH)
    notes: list[str] = Field(default_factory=list, max_length=MAX_NOTES)
    items: list[InvoiceItemInput] = Field(max_length=MAX_INVOICE_ITEMS)

    _normalize_client_name = field_validator("client_name")(_strip_required)
    _normalize_secondary_line = field_validator("secondary_line", "transport")(_strip_optional)

    @field_validator("notes")
    @classmethod
    def normalize_notes(cls, value: list[str]) -> list[str]:
        return _normalize_text_list(value)


class CustomerUpsert(BaseModel):
    id: int | None = None
    name: NonEmptyStr
    secondary_line: str = Field(default="", max_length=MAX_SHORT_TEXT_LENGTH)
    transport: str = Field(default="", max_length=MAX_SHORT_TEXT_LENGTH)
    notes: list[str] = Field(default_factory=list, max_length=MAX_NOTES)
    footer_discounts: list[FooterDiscount] = Field(default_factory=list, max_length=MAX_DISCOUNTS)
    line_discounts_by_format: dict[str, float] = Field(default_factory=dict, max_length=MAX_LINE_DISCOUNT_GROUPS)
    automatic_bonus_rules: list[AutomaticBonusRule] = Field(default_factory=list, max_length=MAX_AUTOMATIC_BONUS_RULES)
    source_count: NonNegativeInt = 0

    _normalize_name = field_validator("name")(_strip_required)
    _normalize_secondary_line = field_validator("secondary_line", "transport")(_strip_optional)

    @field_validator("notes")
    @classmethod
    def normalize_customer_notes(cls, value: list[str]) -> list[str]:
        return _normalize_text_list(value)

    @field_validator("line_discounts_by_format")
    @classmethod
    def validate_line_discounts(cls, value: dict[str, float]) -> dict[str, float]:
        normalized: dict[str, float] = {}
        for key, rate in value.items():
            label = key.strip()
            if not label:
                raise ValueError("discount keys must not be empty")
            if len(label) > MAX_NAME_LENGTH:
                raise ValueError(f"discount keys must be at most {MAX_NAME_LENGTH} characters")
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
    notes: list[str] = Field(default_factory=list, max_length=MAX_NOTES)

    _normalize_name = field_validator("name")(_strip_required)

    @field_validator("notes")
    @classmethod
    def normalize_transport_notes(cls, value: list[str]) -> list[str]:
        return _normalize_text_list(value)


class ProductUpsert(BaseModel):
    id: int | None = None
    name: NonEmptyStr
    aliases: list[str] = Field(default_factory=list, max_length=MAX_ALIASES)

    _normalize_name = field_validator("name")(_strip_required)

    @field_validator("aliases")
    @classmethod
    def normalize_aliases(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if item.strip()]
        for item in normalized:
            if len(item) > MAX_NAME_LENGTH:
                raise ValueError(f"aliases must be at most {MAX_NAME_LENGTH} characters")
        return list(dict.fromkeys(normalized))


class ProductOfferingUpsert(BaseModel):
    id: int | None = None
    label: OfferingLabelStr
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
    automatic_bonus_rules: list[AutomaticBonusRule] = Field(default_factory=list)
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

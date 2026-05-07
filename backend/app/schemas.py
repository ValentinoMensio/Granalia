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
NonNegativeNumber = Annotated[float, Field(ge=0)]


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
    offering_label: str = Field(default="", max_length=120)
    quantity: NonNegativeNumber
    bonus_quantity: NonNegativeInt = 0
    unit_price: NonNegativeInt | None = None

    _normalize_offering_label = field_validator("offering_label")(_strip_optional)

    @field_validator("bonus_quantity", mode="before")
    @classmethod
    def normalize_quantity(cls, value: Any) -> int:
        return round(float(value or 0))


class AutomaticBonusRule(BaseModel):
    product_id: int | None = None
    offering_id: int | None = None
    offering_label: str = Field(default="", max_length=120)
    buy_quantity: int = Field(default=10, ge=1, le=10000)
    bonus_quantity: int = Field(default=1, ge=1, le=10000)

    _normalize_offering_label = field_validator("offering_label")(_strip_optional)


class InvoiceCreate(BaseModel):
    client_name: NonEmptyStr
    date: str = Field(min_length=10, max_length=10)
    price_list_id: int | None = None
    billing_mode: str = "internal_only"
    declared_percentage: float | None = None
    internal_price_list_id: int | None = None
    fiscal_price_list_id: int | None = None
    declared: bool = False
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

    @field_validator("billing_mode")
    @classmethod
    def validate_billing_mode(cls, value: str) -> str:
        if value not in {"internal_only", "fiscal_only", "split"}:
            raise ValueError("billing_mode must be internal_only, fiscal_only or split")
        return value

    @field_validator("declared_percentage")
    @classmethod
    def validate_declared_percentage(cls, value: float | None) -> float | None:
        if value is None:
            return None
        numeric = float(value)
        if numeric < 0 or numeric > 100:
            raise ValueError("declared_percentage must be between 0 and 100")
        return numeric


class CustomerUpsert(BaseModel):
    id: int | None = None
    name: NonEmptyStr
    cuit: str = Field(default="", max_length=32)
    address: str = Field(default="", max_length=MAX_SHORT_TEXT_LENGTH)
    business_name: str = Field(default="", max_length=MAX_NAME_LENGTH)
    email: str = Field(default="", max_length=MAX_NAME_LENGTH)
    secondary_line: str = Field(default="", max_length=MAX_SHORT_TEXT_LENGTH)
    transport: str = Field(default="", max_length=MAX_SHORT_TEXT_LENGTH)
    notes: list[str] = Field(default_factory=list, max_length=MAX_NOTES)
    footer_discounts: list[FooterDiscount] = Field(default_factory=list, max_length=MAX_DISCOUNTS)
    line_discounts_by_format: dict[str, float] = Field(default_factory=dict, max_length=MAX_LINE_DISCOUNT_GROUPS)
    automatic_bonus_rules: list[AutomaticBonusRule] = Field(default_factory=list, max_length=MAX_AUTOMATIC_BONUS_RULES)
    automatic_bonus_disables_line_discount: bool = False
    source_count: NonNegativeInt = 0

    _normalize_name = field_validator("name")(_strip_required)
    _normalize_optional_text = field_validator("cuit", "address", "business_name", "email", "secondary_line", "transport")(_strip_optional)

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


class AuthorizationPayload(BaseModel):
    password: str = Field(min_length=1, max_length=500)


class ArcaAuthorizationOut(BaseModel):
    invoice_id: int
    fiscal_status: str
    arca_request_id: int
    message: str


class InvoiceRequest(BaseModel):
    order: InvoiceCreate
    profile: CustomerUpsert
    authorization: AuthorizationPayload | None = None


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
    iva_rate: float | None = None

    _normalize_name = field_validator("name")(_strip_required)

    @field_validator("aliases")
    @classmethod
    def normalize_aliases(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if item.strip()]
        for item in normalized:
            if len(item) > MAX_NAME_LENGTH:
                raise ValueError(f"aliases must be at most {MAX_NAME_LENGTH} characters")
        return list(dict.fromkeys(normalized))

    @field_validator("iva_rate")
    @classmethod
    def validate_iva_rate(cls, value: float | None) -> float | None:
        if value is None:
            return None
        numeric = round(float(value), 3)
        if numeric not in (0.105, 0.21):
            raise ValueError("iva_rate must be 0.105 or 0.21")
        return numeric


class ProductOfferingUpsert(BaseModel):
    id: int | None = None
    label: OfferingLabelStr
    price: NonNegativeInt
    net_weight_kg: NonNegativeNumber = 0

    _normalize_label = field_validator("label")(_strip_required)


class PriceListProductUpdate(BaseModel):
    product: ProductUpsert
    offerings: list[ProductOfferingUpsert] = Field(default_factory=list, max_length=MAX_PRODUCT_OFFERINGS)


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
    net_weight_kg: float = 0


class ProductCatalogOut(BaseModel):
    id: int
    name: str
    aliases: list[str] = Field(default_factory=list)
    iva_rate: float | None = None
    offerings: list[ProductOfferingOut] = Field(default_factory=list)


class ProductOut(BaseModel):
    id: int
    name: str
    aliases: list[str] = Field(default_factory=list)
    iva_rate: float | None = None
    active: bool
    created_at: str
    updated_at: str


class CustomerOut(BaseModel):
    id: int
    name: str
    cuit: str = ""
    address: str = ""
    business_name: str = ""
    email: str = ""
    secondary_line: str = ""
    transport: str = ""
    notes: list[str] = Field(default_factory=list)
    footer_discounts: list[FooterDiscount] = Field(default_factory=list)
    line_discounts_by_format: dict[str, float] = Field(default_factory=dict)
    automatic_bonus_rules: list[AutomaticBonusRule] = Field(default_factory=list)
    automatic_bonus_disables_line_discount: bool = False
    source_count: int = 0
    transport_id: int | None = None
    created_at: str
    updated_at: str


class PriceListMetaOut(BaseModel):
    id: int
    name: str
    filename: str
    content_type: str
    size: int
    active: bool
    source: str
    uploaded_at: str
    updated_at: str


class PriceListRename(BaseModel):
    name: NonEmptyStr

    _normalize_name = field_validator("name")(_strip_required)


class DatabaseInfoOut(BaseModel):
    type: str
    url: str


class BootstrapOut(BaseModel):
    catalog: list[ProductCatalogOut] = Field(default_factory=list)
    profiles: dict[str, CustomerOut] = Field(default_factory=dict)
    clients: list[str] = Field(default_factory=list)
    transports: list[TransportOut] = Field(default_factory=list)
    price_lists: list[PriceListMetaOut] = Field(default_factory=list)
    price_list: PriceListMetaOut | None = None
    database: DatabaseInfoOut


class CustomerMutationOut(BaseModel):
    customer: CustomerOut
    bootstrap: BootstrapOut


class InvoiceSummaryOut(BaseModel):
    gross_total: int
    discount_total: int
    final_total: int
    total_bultos: float


class InvoiceListItemOut(BaseModel):
    invoice_id: int
    batch_id: int | None = None
    document_type: str = "FACTURA"
    point_of_sale: int = 1
    invoice_number: int | None = None
    internal_invoice_number: int | None = None
    fiscal_number: str = ""
    customer_id: int | None = None
    transport_id: int | None = None
    client_name: str
    transport: str = ""
    order_date: str
    price_list_id: int | None = None
    price_list_name: str = ""
    price_list_effective_date: str | None = None
    declared: bool = False
    split_kind: str | None = None
    split_percentage: float | None = None
    fiscal_status: str = "internal"
    arca_environment: str | None = None
    arca_point_of_sale: int | None = None
    arca_invoice_number: int | None = None
    arca_cae: str | None = None
    arca_cae_expires_at: str | None = None
    arca_error_code: str | None = None
    arca_error_message: str | None = None
    total_bultos: float
    gross_total: int
    discount_total: int
    final_total: int
    fiscal_total: float | None = None
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
    quantity: float
    unit_price: int
    gross: int
    discount: int
    total: int
    effective_discount: int | None = None
    effective_total: int | None = None
    product_name: str | None = None
    offering_label: str | None = None
    offering_net_weight_kg: float = 0
    line_type: str = "sale"
    discount_rate: float = 0
    iva_rate: float | None = None
    net_amount: float | None = None
    iva_amount: float | None = None
    fiscal_total: float | None = None


class InvoiceDetailOut(BaseModel):
    id: int
    batch_id: int | None = None
    document_type: str = "FACTURA"
    point_of_sale: int = 1
    invoice_number: int | None = None
    internal_invoice_number: int | None = None
    fiscal_number: str = ""
    customer_id: int | None = None
    transport_id: int | None = None
    legacy_key: str | None = None
    client_name: str
    order_date: str
    price_list_id: int | None = None
    price_list_name: str = ""
    price_list_effective_date: str | None = None
    declared: bool = False
    split_kind: str | None = None
    split_percentage: float | None = None
    fiscal_status: str = "internal"
    fiscal_locked_at: str | None = None
    fiscal_authorized_at: str | None = None
    arca_environment: str | None = None
    arca_cuit_emisor: str | None = None
    arca_cbte_tipo: int | None = None
    arca_concepto: int | None = None
    arca_doc_tipo: int | None = None
    arca_doc_nro: str | None = None
    arca_point_of_sale: int | None = None
    arca_invoice_number: int | None = None
    arca_cae: str | None = None
    arca_cae_expires_at: str | None = None
    arca_result: str | None = None
    arca_observations: Any | None = None
    arca_error_code: str | None = None
    arca_error_message: str | None = None
    arca_request_id: str | None = None
    secondary_line: str = ""
    transport: str = ""
    notes: list[str] = Field(default_factory=list)
    footer_discounts: list[FooterDiscount] = Field(default_factory=list)
    line_discounts_by_format: dict[str, float] = Field(default_factory=dict)
    total_bultos: float
    gross_total: int
    discount_total: int
    final_total: int
    output_filename: str
    xlsx_size: int
    created_at: str
    customer_name: str | None = None
    customer_cuit: str | None = None
    customer_address: str | None = None
    customer_business_name: str | None = None
    customer_iva_condition: str | None = None
    customer_email: str | None = None
    transport_name: str | None = None
    items: list[InvoiceItemOut] = Field(default_factory=list)


class InvoiceCreateOut(BaseModel):
    invoice_id: int
    batch_id: int | None = None
    invoices: list[dict[str, Any]] = Field(default_factory=list)
    filename: str
    download_url: str
    summary: InvoiceSummaryOut


class AuthSessionOut(BaseModel):
    authenticated: bool
    username: str | None = None
    role: str | None = None
    csrf_token: str | None = None


class HealthOut(BaseModel):
    status: str


class PriceListUploadOut(BaseModel):
    bootstrap: BootstrapOut

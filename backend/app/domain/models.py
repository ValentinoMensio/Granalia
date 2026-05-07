from __future__ import annotations

from dataclasses import asdict, dataclass, field

from ..types import (
    CatalogOfferingData,
    CatalogProductData,
    CustomerProfileData,
    FooterDiscountData,
    AutomaticBonusRuleData,
    InvoiceRowData,
    InvoiceSnapshotData,
    InvoiceSummaryData,
    OrderData,
    OrderItemData,
)


@dataclass(slots=True)
class FooterDiscount:
    label: str
    rate: float

    @classmethod
    def from_data(cls, data: FooterDiscountData) -> "FooterDiscount":
        return cls(label=str(data["label"]), rate=float(data["rate"]))

    def to_data(self) -> FooterDiscountData:
        return {"label": self.label, "rate": self.rate}


@dataclass(slots=True)
class AutomaticBonusRule:
    product_id: int | None = None
    offering_id: int | None = None
    offering_label: str = ""
    buy_quantity: int = 10
    bonus_quantity: int = 1

    @classmethod
    def from_data(cls, data: AutomaticBonusRuleData) -> "AutomaticBonusRule":
        product_id = data.get("product_id")
        offering_id = data.get("offering_id")
        return cls(
            product_id=int(product_id) if product_id is not None else None,
            offering_id=int(offering_id) if offering_id is not None else None,
            offering_label=str(data.get("offering_label") or ""),
            buy_quantity=int(data.get("buy_quantity") or 10),
            bonus_quantity=int(data.get("bonus_quantity") or 1),
        )

    def to_data(self) -> AutomaticBonusRuleData:
        return asdict(self)


@dataclass(slots=True)
class CatalogOffering:
    id: int | str
    label: str
    price: int
    net_weight_kg: float = 0

    @classmethod
    def from_data(cls, data: CatalogOfferingData) -> "CatalogOffering":
        return cls(id=data["id"], label=str(data["label"]), price=int(data["price"]), net_weight_kg=float(data.get("net_weight_kg") or 0))

    def to_data(self) -> CatalogOfferingData:
        return {"id": self.id, "label": self.label, "price": self.price, "net_weight_kg": self.net_weight_kg}


@dataclass(slots=True)
class CatalogProduct:
    id: int | str
    name: str
    aliases: list[str] = field(default_factory=list)
    offerings: list[CatalogOffering] = field(default_factory=list)
    iva_rate: float | None = None

    @classmethod
    def from_data(cls, data: CatalogProductData) -> "CatalogProduct":
        return cls(
            id=data["id"],
            name=str(data["name"]),
            aliases=[str(item) for item in data.get("aliases", [])],
            offerings=[CatalogOffering.from_data(item) for item in data.get("offerings", [])],
            iva_rate=float(data["iva_rate"]) if data.get("iva_rate") is not None else None,
        )

    def to_data(self) -> CatalogProductData:
        return {
            "id": self.id,
            "name": self.name,
            "aliases": list(self.aliases),
            "offerings": [item.to_data() for item in self.offerings],
            "iva_rate": self.iva_rate,
        }


@dataclass(slots=True)
class OrderItem:
    product_id: int
    offering_id: int
    quantity: float
    bonus_quantity: int = 0
    unit_price: int | None = None
    offering_label: str = ""

    @classmethod
    def from_data(cls, data: OrderItemData) -> "OrderItem":
        return cls(
            product_id=int(data["product_id"]),
            offering_id=int(data["offering_id"]),
            offering_label=str(data.get("offering_label") or ""),
            quantity=float(data["quantity"]),
            bonus_quantity=int(data.get("bonus_quantity", 0)),
            unit_price=int(data["unit_price"]) if data.get("unit_price") is not None else None,
        )

    def to_data(self) -> OrderItemData:
        return asdict(self)


@dataclass(slots=True)
class CustomerProfile:
    name: str
    secondary_line: str = ""
    transport: str = ""
    notes: list[str] = field(default_factory=list)
    footer_discounts: list[FooterDiscount] = field(default_factory=list)
    line_discounts_by_format: dict[str, float] = field(default_factory=dict)
    automatic_bonus_rules: list[AutomaticBonusRule] = field(default_factory=list)
    automatic_bonus_disables_line_discount: bool = False
    source_count: int = 0

    @classmethod
    def from_data(cls, data: CustomerProfileData) -> "CustomerProfile":
        return cls(
            name=str(data["name"]),
            secondary_line=str(data.get("secondary_line", "")),
            transport=str(data.get("transport", "")),
            notes=[str(item) for item in data.get("notes", [])],
            footer_discounts=[FooterDiscount.from_data(item) for item in data.get("footer_discounts", [])],
            line_discounts_by_format={str(key): float(value) for key, value in data.get("line_discounts_by_format", {}).items()},
            automatic_bonus_rules=[AutomaticBonusRule.from_data(item) for item in data.get("automatic_bonus_rules", [])],
            automatic_bonus_disables_line_discount=bool(data.get("automatic_bonus_disables_line_discount", False)),
            source_count=int(data.get("source_count", 0)),
        )

    def to_data(self) -> CustomerProfileData:
        return {
            "name": self.name,
            "secondary_line": self.secondary_line,
            "transport": self.transport,
            "notes": list(self.notes),
            "footer_discounts": [item.to_data() for item in self.footer_discounts],
            "line_discounts_by_format": dict(self.line_discounts_by_format),
            "automatic_bonus_rules": [item.to_data() for item in self.automatic_bonus_rules],
            "automatic_bonus_disables_line_discount": self.automatic_bonus_disables_line_discount,
            "source_count": self.source_count,
        }


@dataclass(slots=True)
class Order:
    client_name: str
    date: str
    secondary_line: str = ""
    transport: str = ""
    notes: list[str] = field(default_factory=list)
    items: list[OrderItem] = field(default_factory=list)

    @classmethod
    def from_data(cls, data: OrderData) -> "Order":
        return cls(
            client_name=str(data["client_name"]),
            date=str(data["date"]),
            secondary_line=str(data.get("secondary_line", "")),
            transport=str(data.get("transport", "")),
            notes=[str(item) for item in data.get("notes", [])],
            items=[OrderItem.from_data(item) for item in data.get("items", [])],
        )

    def to_data(self) -> OrderData:
        return {
            "client_name": self.client_name,
            "date": self.date,
            "secondary_line": self.secondary_line,
            "transport": self.transport,
            "notes": list(self.notes),
            "items": [item.to_data() for item in self.items],
        }


@dataclass(slots=True)
class InvoiceRow:
    product_id: int | None
    offering_id: int | None
    product_name: str
    offering_label: str
    offering_net_weight_kg: float
    line_type: str
    discount_rate: float
    label: str
    quantity: float
    unit_price: int
    gross: int
    discount: int
    total: int

    def to_data(self) -> InvoiceRowData:
        return asdict(self)


@dataclass(slots=True)
class InvoiceSummary:
    gross_total: int
    discount_total: int
    final_total: int
    total_bultos: float

    def to_data(self) -> InvoiceSummaryData:
        return asdict(self)


@dataclass(slots=True)
class InvoiceSnapshot:
    rows: list[InvoiceRow]
    summary: InvoiceSummary
    order: Order
    profile: CustomerProfile

    def to_data(self) -> InvoiceSnapshotData:
        return {
            "rows": [row.to_data() for row in self.rows],
            "summary": self.summary.to_data(),
            "order": self.order.to_data(),
            "profile": self.profile.to_data(),
        }

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class ArcaIvaItem:
    Id: int
    BaseImp: Decimal
    Importe: Decimal


@dataclass(frozen=True)
class ArcaInvoiceItem:
    code: str
    description: str
    quantity: Decimal
    unit_code: int
    unit_price: Decimal
    discount_amount: Decimal
    iva_id: int
    iva_amount: Decimal
    item_total: Decimal


@dataclass(frozen=True)
class ArcaInvoiceRequest:
    invoice_id: int
    point_of_sale: int
    cbte_tipo: int
    concepto: int
    doc_tipo: int
    doc_nro: str
    condicion_iva_receptor_id: int
    imp_neto: Decimal
    imp_iva: Decimal
    imp_total: Decimal
    iva: list[ArcaIvaItem]
    items: list[ArcaInvoiceItem]


@dataclass(frozen=True)
class ArcaAuthTicket:
    token: str
    sign: str
    expiration_time: str


@dataclass(frozen=True)
class ArcaAuthorizationResult:
    result: str
    invoice_number: int | None
    cae: str | None
    cae_expires_at: date | None
    observations: list[dict[str, object]]
    raw: dict[str, object]

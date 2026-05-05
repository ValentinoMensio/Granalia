from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ArcaIvaItem:
    Id: int
    BaseImp: Decimal
    Importe: Decimal


@dataclass(frozen=True)
class ArcaInvoiceRequest:
    invoice_id: int
    point_of_sale: int
    cbte_tipo: int
    concepto: int
    doc_tipo: int
    doc_nro: str
    imp_neto: Decimal
    imp_iva: Decimal
    imp_total: Decimal
    iva: list[ArcaIvaItem]

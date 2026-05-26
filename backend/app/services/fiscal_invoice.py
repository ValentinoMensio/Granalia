from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from .arca.client import ArcaClient
from .arca.config import get_arca_config
from .arca.padron import lookup_taxpayer_data
from .invoicing import generate_invoice_document


FISCAL_DRAFT_STATUSES = {"draft", "authorization_failed", "rejected", "error"}
FISCAL_STATUSES = FISCAL_DRAFT_STATUSES | {"authorizing", "authorized", "authorized_homologation"}


@dataclass(frozen=True)
class FiscalInvoicePrepared:
    snapshot: dict


def digits_only(value: object) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def is_fiscal_invoice(invoice: dict) -> bool:
    return bool(invoice.get("declared")) or invoice.get("split_kind") == "fiscal"


def is_invoice_fiscally_locked(invoice: dict) -> bool:
    environment = str(invoice.get("arca_environment") or "")
    return str(invoice.get("fiscal_status") or "") == "authorized" and environment in {"produccion", "production"}


def fallback_iva_condition_id(value: object) -> int | None:
    text = " ".join(str(value or "").lower().replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u").split())
    if "responsable" in text and "inscrip" in text:
        return 1
    if "monotrib" in text:
        return 6
    if "consumidor" in text and "final" in text:
        return 5
    if "exento" in text:
        return 4
    return None


class FiscalInvoiceService:
    def __init__(self, repository) -> None:
        self.repository = repository

    def prepare_fiscal_invoice(self, order: dict, profile: dict, catalog: list[dict]) -> FiscalInvoicePrepared:
        padron_result = self.validate_customer_source(profile)
        self.validate_customer_fiscal_data(profile)
        iva_condition_id = self.resolve_receiver_iva_condition_id(profile)
        self.validate_invoice_a_receiver(profile, iva_condition_id)
        snapshot = generate_invoice_document(order, profile, catalog)
        snapshot = self.build_fiscalized_snapshot(snapshot, catalog)
        snapshot["customer_fiscal_snapshot"] = self.build_customer_fiscal_snapshot(profile, iva_condition_id, padron_result)
        self.validate_tax_breakdown(snapshot)
        return FiscalInvoicePrepared(snapshot=snapshot)

    def validate_customer_fiscal_data(self, profile: dict) -> None:
        cuit = digits_only(profile.get("cuit"))
        if len(cuit) != 11:
            raise ValueError("Cliente fiscal con CUIT invalido")
        if not str(profile.get("business_name") or profile.get("name") or "").strip():
            raise ValueError("Cliente fiscal sin razon social")
        if not str(profile.get("address") or "").strip():
            raise ValueError("Cliente fiscal sin domicilio")
        if not str(profile.get("iva_condition") or "").strip():
            raise ValueError("Cliente fiscal sin condicion IVA")

    def validate_customer_source(self, profile: dict) -> dict[str, object] | None:
        environment = os.getenv("GRANALIA_ARCA_ENV", "homologacion").strip().lower() or "homologacion"
        allow_manual = os.getenv("GRANALIA_ARCA_ALLOW_MANUAL_FISCAL_CUSTOMER", "false").strip().lower() == "true"
        if environment in {"produccion", "production"} and allow_manual:
            raise ValueError("En produccion no se permiten clientes fiscales manuales")
        if allow_manual:
            return None
        cuit = digits_only(profile.get("cuit"))
        result = lookup_taxpayer_data(cuit)
        if not result.get("ok"):
            raise ValueError(f"No se pudo validar el cliente fiscal contra ARCA: {result.get('error') or 'sin datos'}")
        return result

    def sync_receiver_iva_conditions(self) -> None:
        config = get_arca_config()
        if not config.is_configured:
            return
        conditions = ArcaClient(config).get_receiver_iva_conditions()
        self.repository.upsert_arca_iva_conditions(conditions)

    def resolve_receiver_iva_condition_id(self, profile: dict) -> int:
        iva_condition = str(profile.get("iva_condition") or "").strip()
        if not iva_condition:
            raise ValueError("Falta condicion IVA del receptor")
        condition_id = self.repository.resolve_arca_iva_condition_id(iva_condition)
        if condition_id is None:
            try:
                self.sync_receiver_iva_conditions()
            except Exception:
                pass
            condition_id = self.repository.resolve_arca_iva_condition_id(iva_condition)
        if condition_id is None and os.getenv("GRANALIA_ARCA_ALLOW_MANUAL_FISCAL_CUSTOMER", "false").strip().lower() == "true":
            condition_id = fallback_iva_condition_id(iva_condition) or int(os.getenv("GRANALIA_ARCA_RECEIVER_IVA_CONDITION_ID", "1") or "1")
        if condition_id is None:
            raise ValueError("Condicion IVA receptor no mapeada para ARCA")
        return int(condition_id)

    def validate_invoice_a_receiver(self, profile: dict, iva_condition_id: int) -> None:
        iva_condition = str(profile.get("iva_condition") or "").lower()
        if iva_condition_id == 5 or "consumidor final" in iva_condition:
            raise ValueError("Factura A no corresponde para consumidor final")

    def build_customer_fiscal_snapshot(self, profile: dict, iva_condition_id: int, padron_result: dict[str, object] | None) -> dict[str, object]:
        padron_data = padron_result.get("data") if isinstance(padron_result, dict) else None
        return {
            "doc_tipo": 80,
            "doc_nro": digits_only(profile.get("cuit")),
            "fiscal_name": str(profile.get("business_name") or profile.get("name") or "").strip(),
            "iva_condition": str(profile.get("iva_condition") or "").strip(),
            "condicion_iva_receptor_id": int(iva_condition_id),
            "fiscal_address": str(profile.get("address") or "").strip(),
            "padron_checked_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat() if padron_result else None,
            "padron_ok": bool(padron_result.get("ok")) if isinstance(padron_result, dict) else False,
            "padron_environment": padron_result.get("environment") if isinstance(padron_result, dict) else None,
            "padron_data": padron_data if isinstance(padron_data, dict) else None,
        }

    def build_fiscalized_snapshot(self, snapshot: dict, catalog: list[dict]) -> dict:
        products_by_id = {str(product.get("id")): product for product in catalog}
        rows = []
        for row in snapshot.get("rows", []):
            next_row = dict(row)
            if row.get("product_id") is None and row.get("iva_rate") is not None:
                rows.append(next_row)
                continue
            product = products_by_id.get(str(row.get("product_id") or ""))
            if not product:
                raise ValueError(f"Producto fiscal no encontrado para {row.get('product_name') or row.get('label')}")
            iva_rate = product.get("iva_rate")
            if iva_rate is None:
                raise ValueError(f"Falta configurar IVA fiscal para {product.get('name')}")
            next_row["iva_rate"] = float(iva_rate)
            rows.append(next_row)
        return {**snapshot, "rows": rows}

    def validate_tax_breakdown(self, snapshot: dict) -> None:
        breakdown: dict[Decimal, dict[str, Decimal]] = {}
        for row in snapshot.get("rows", []):
            iva_rate = row.get("iva_rate")
            if iva_rate is None:
                raise ValueError(f"Falta IVA fiscal para {row.get('label')}")
            quantity = Decimal(str(row.get("quantity") or 0))
            if quantity <= 0:
                continue
            net_amount = Decimal(str(row.get("total") or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            rate = Decimal(str(iva_rate))
            iva_amount = (net_amount * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            current = breakdown.setdefault(rate, {"base": Decimal("0"), "iva": Decimal("0")})
            current["base"] += net_amount
            current["iva"] += iva_amount
        if not breakdown:
            raise ValueError("La factura fiscal no tiene base imponible")

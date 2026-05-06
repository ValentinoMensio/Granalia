from __future__ import annotations

import os
import hashlib
import json
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, datetime
from typing import cast

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Engine
from sqlalchemy.sql.schema import Table

from ..core.utils import canonicalize_discount_config
from ..types import CustomerProfileData, InvoiceDetailData, InvoiceFileData, InvoiceListItemData, InvoiceSnapshotData, OrderData
from .postgres_protocol import PostgresRepositoryProtocol
from .postgres_utils import serialize_value, utc_now


class PostgresInvoiceMixin(PostgresRepositoryProtocol):
    engine: Engine
    invoices: Table
    customers: Table
    transports: Table
    invoice_items: Table
    products: Table
    product_offerings: Table
    invoice_batches: Table
    price_lists: Table
    invoice_tax_breakdown: Table
    arca_requests: Table
    invoice_sequences: Table

    def _round_money(self, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _fiscal_item_values(self, item: dict[str, object]) -> dict[str, object]:
        iva_rate = item.get("iva_rate")
        if iva_rate is None:
            return {}
        net_amount = self._round_money(Decimal(str(item.get("total") or 0)))
        iva_amount = self._round_money(net_amount * Decimal(str(iva_rate)))
        return {
            "iva_rate": Decimal(str(iva_rate)),
            "net_amount": net_amount,
            "iva_amount": iva_amount,
            "fiscal_total": self._round_money(net_amount + iva_amount),
        }

    def _arca_iva_id(self, iva_rate: Decimal) -> int:
        return 4 if iva_rate == Decimal("0.105") else 5

    def _fiscal_scope(self) -> tuple[str, int]:
        document_type = os.getenv("GRANALIA_DOCUMENT_TYPE", "FACTURA").strip().upper() or "FACTURA"
        point_of_sale = int(os.getenv("GRANALIA_POINT_OF_SALE", "1") or "1")
        if point_of_sale <= 0:
            raise ValueError("GRANALIA_POINT_OF_SALE debe ser positivo")
        return document_type, point_of_sale

    def _format_fiscal_number(self, document_type: str, point_of_sale: int, invoice_number: int) -> str:
        return f"{document_type} {point_of_sale:04d}-{invoice_number:08d}"

    def _next_fiscal_number(self, *, connection, document_type: str, point_of_sale: int, now) -> int:
        stmt = insert(self.invoice_sequences).values(
            document_type=document_type,
            point_of_sale=point_of_sale,
            next_number=1,
            created_at=now,
            updated_at=now,
        )
        stmt = stmt.on_conflict_do_nothing(index_elements=[self.invoice_sequences.c.document_type, self.invoice_sequences.c.point_of_sale])
        connection.execute(stmt)
        row = connection.execute(
            select(self.invoice_sequences.c.next_number)
            .where(
                self.invoice_sequences.c.document_type == document_type,
                self.invoice_sequences.c.point_of_sale == point_of_sale,
            )
            .with_for_update()
        ).mappings().first()
        if not row:
            raise ValueError("No se pudo resolver la secuencia fiscal")
        invoice_number = int(row["next_number"])
        connection.execute(
            update(self.invoice_sequences)
            .where(
                self.invoice_sequences.c.document_type == document_type,
                self.invoice_sequences.c.point_of_sale == point_of_sale,
            )
            .values(next_number=invoice_number + 1, updated_at=now)
        )
        return invoice_number

    def list_invoices(self, limit: int = 50, date_from: date | None = None) -> list[InvoiceListItemData]:
        with self.engine.connect() as connection:
            query = (
                select(
                    self.invoices.c.id.label("invoice_id"),
                    self.invoices.c.batch_id,
                    self.invoices.c.document_type,
                    self.invoices.c.point_of_sale,
                    self.invoices.c.invoice_number,
                    self.invoices.c.customer_id,
                    self.invoices.c.transport_id,
                    self.invoices.c.client_name,
                    self.invoices.c.transport,
                    self.invoices.c.order_date,
                    self.invoices.c.price_list_id,
                    self.invoices.c.price_list_name,
                    self.invoices.c.price_list_effective_date,
                    self.invoices.c.declared,
                    self.invoices.c.split_kind,
                    self.invoices.c.split_percentage,
                    self.invoices.c.fiscal_status,
                    self.invoices.c.arca_environment,
                    self.invoices.c.arca_point_of_sale,
                    self.invoices.c.arca_invoice_number,
                    self.invoices.c.arca_cae,
                    self.invoices.c.arca_cae_expires_at,
                    self.invoices.c.arca_error_code,
                    self.invoices.c.arca_error_message,
                    self.invoices.c.total_bultos,
                    self.invoices.c.gross_total,
                    self.invoices.c.discount_total,
                    self.invoices.c.final_total,
                    self.invoices.c.output_filename,
                    self.invoices.c.xlsx_size,
                    self.invoices.c.created_at,
                )
                .order_by(self.invoices.c.order_date.desc(), self.invoices.c.id.desc())
                .limit(limit)
            )
            if date_from is not None:
                query = query.where(self.invoices.c.order_date >= date_from)
            rows = connection.execute(query).mappings().all()
        payload: list[InvoiceListItemData] = cast(list[InvoiceListItemData], [{key: serialize_value(value) for key, value in row.items()} for row in rows])
        for item in payload:
            item["fiscal_number"] = self._format_fiscal_number(str(item.get("document_type") or "FACTURA"), int(item.get("point_of_sale") or 1), int(item.get("invoice_number") or 0))
        invoice_ids = [int(item["invoice_id"]) for item in payload if bool(item.get("declared")) or item.get("split_kind") == "fiscal"]
        if invoice_ids:
            with self.engine.connect() as connection:
                item_rows = connection.execute(
                    select(
                        self.invoice_items.c.invoice_id,
                        self.invoice_items.c.gross,
                        self.invoice_items.c.discount,
                        self.invoice_items.c.total,
                        self.invoice_items.c.iva_rate,
                    ).where(self.invoice_items.c.invoice_id.in_(invoice_ids))
                ).mappings().all()
            items_by_invoice: dict[int, list[dict[str, object]]] = {}
            for row in item_rows:
                items_by_invoice.setdefault(int(row["invoice_id"]), []).append({key: serialize_value(value) for key, value in row.items()})
            discounts_by_invoice = {int(item["invoice_id"]): int(item.get("discount_total") or 0) for item in payload}
            for invoice_id, invoice_items in items_by_invoice.items():
                current_discount = sum(int(item.get("discount") or 0) for item in invoice_items)
                delta = discounts_by_invoice.get(invoice_id, current_discount) - current_discount
                allocations = self._allocate_integer_amount(delta, [int(item.get("gross") or 0) for item in invoice_items])
                fiscal_total = Decimal("0")
                for invoice_item, allocation in zip(invoice_items, allocations):
                    if invoice_item.get("iva_rate") is None:
                        continue
                    net_amount = Decimal(str(int(invoice_item.get("total") or 0) - allocation))
                    fiscal_total += self._round_money(net_amount * (Decimal("1") + Decimal(str(invoice_item["iva_rate"]))))
                for item in payload:
                    if int(item["invoice_id"]) == invoice_id:
                        item["fiscal_total"] = float(fiscal_total)
        return payload

    def list_invoice_item_stats(self) -> list[dict[str, object]]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(
                    self.invoices.c.id.label("invoice_id"),
                    self.invoices.c.document_type,
                    self.invoices.c.point_of_sale,
                    self.invoices.c.invoice_number,
                    self.invoices.c.customer_id,
                    self.invoices.c.transport_id,
                    self.invoices.c.client_name,
                    self.invoices.c.transport,
                    self.invoices.c.order_date,
                    self.invoices.c.price_list_effective_date,
                    self.invoices.c.gross_total.label("invoice_gross_total"),
                    self.invoices.c.discount_total.label("invoice_discount_total"),
                    self.invoices.c.final_total.label("invoice_final_total"),
                    self.invoice_items.c.product_id,
                    self.invoice_items.c.offering_id,
                    self.invoice_items.c.product_name,
                    self.invoice_items.c.offering_label,
                    self.invoice_items.c.offering_net_weight_kg,
                    self.invoice_items.c.line_type,
                    self.invoice_items.c.discount_rate,
                    self.invoice_items.c.label,
                    self.invoice_items.c.quantity,
                    self.invoice_items.c.unit_price,
                    self.invoice_items.c.gross,
                    self.invoice_items.c.discount,
                    self.invoice_items.c.total,
                )
                .select_from(
                    self.invoice_items
                    .join(self.invoices, self.invoice_items.c.invoice_id == self.invoices.c.id)
                )
                .order_by(self.invoices.c.order_date.desc(), self.invoices.c.id.desc(), self.invoice_items.c.line_number)
            ).mappings().all()
        items = [{key: serialize_value(value) for key, value in row.items()} for row in rows]
        items_by_invoice: dict[str, list[dict[str, object]]] = {}
        for item in items:
            items_by_invoice.setdefault(str(item.get("invoice_id") or ""), []).append(item)

        for invoice_items in items_by_invoice.values():
            current_discount = sum(int(item.get("discount") or 0) for item in invoice_items)
            invoice_discount = int(invoice_items[0].get("invoice_discount_total") or current_discount)
            delta = invoice_discount - current_discount
            allocations = self._allocate_integer_amount(delta, [int(item.get("gross") or 0) for item in invoice_items])
            for item, allocation in zip(invoice_items, allocations):
                effective_discount = int(item.get("discount") or 0) + allocation
                item["effective_discount"] = effective_discount
                item["effective_total"] = int(item.get("gross") or 0) - effective_discount

        return items

    def _allocate_integer_amount(self, total: int, weights: list[int]) -> list[int]:
        sign = -1 if total < 0 else 1
        absolute_total = abs(int(total or 0))
        positive_weights = [max(0, int(weight or 0)) for weight in weights]
        weight_total = sum(positive_weights)

        if not absolute_total or not weight_total:
            return [0 for _ in weights]

        shares = []
        for index, weight in enumerate(positive_weights):
            raw = absolute_total * weight / weight_total
            base = int(raw)
            shares.append({"index": index, "base": base, "remainder": raw - base})

        assigned = sum(item["base"] for item in shares)
        shares.sort(key=lambda item: (-float(item["remainder"]), int(item["index"])))
        for item in shares:
            if assigned >= absolute_total:
                break
            item["base"] += 1
            assigned += 1

        shares.sort(key=lambda item: int(item["index"]))
        return [int(item["base"]) * sign for item in shares]

    def get_invoice_detail(self, invoice_id: int) -> InvoiceDetailData | None:
        with self.engine.connect() as connection:
            invoice_row = connection.execute(
                select(
                    self.invoices.c.id,
                    self.invoices.c.batch_id,
                    self.invoices.c.document_type,
                    self.invoices.c.point_of_sale,
                    self.invoices.c.invoice_number,
                    self.invoices.c.customer_id,
                    self.invoices.c.transport_id,
                    self.invoices.c.legacy_key,
                    self.invoices.c.client_name,
                    self.invoices.c.order_date,
                    self.invoices.c.price_list_id,
                    self.invoices.c.price_list_name,
                    self.invoices.c.price_list_effective_date,
                    self.invoices.c.customer_cuit,
                    self.invoices.c.customer_address,
                    self.invoices.c.customer_business_name,
                    self.invoices.c.customer_email,
                    self.invoices.c.declared,
                    self.invoices.c.split_kind,
                    self.invoices.c.split_percentage,
                    self.invoices.c.fiscal_status,
                    self.invoices.c.fiscal_locked_at,
                    self.invoices.c.fiscal_authorized_at,
                    self.invoices.c.arca_environment,
                    self.invoices.c.arca_cuit_emisor,
                    self.invoices.c.arca_cbte_tipo,
                    self.invoices.c.arca_concepto,
                    self.invoices.c.arca_doc_tipo,
                    self.invoices.c.arca_doc_nro,
                    self.invoices.c.arca_point_of_sale,
                    self.invoices.c.arca_invoice_number,
                    self.invoices.c.arca_cae,
                    self.invoices.c.arca_cae_expires_at,
                    self.invoices.c.arca_result,
                    self.invoices.c.arca_observations,
                    self.invoices.c.arca_error_code,
                    self.invoices.c.arca_error_message,
                    self.invoices.c.arca_request_id,
                    self.invoices.c.secondary_line,
                    self.invoices.c.transport,
                    self.invoices.c.notes,
                    self.invoices.c.footer_discounts,
                    self.invoices.c.line_discounts_by_format,
                    self.invoices.c.total_bultos,
                    self.invoices.c.gross_total,
                    self.invoices.c.discount_total,
                    self.invoices.c.final_total,
                    self.invoices.c.output_filename,
                    self.invoices.c.xlsx_size,
                    self.invoices.c.created_at,
                    self.invoices.c.client_name.label("customer_name"),
                    self.invoices.c.transport.label("transport_name"),
                )
                .select_from(self.invoices)
                .where(self.invoices.c.id == invoice_id)
            ).mappings().first()
            if not invoice_row:
                return None

            item_rows = connection.execute(
                select(
                    self.invoice_items,
                    self.products.c.iva_rate.label("product_iva_rate"),
                )
                .select_from(self.invoice_items.outerjoin(self.products, self.invoice_items.c.product_id == self.products.c.id))
                .where(self.invoice_items.c.invoice_id == invoice_id)
                .order_by(self.invoice_items.c.line_number)
            ).mappings().all()

        invoice = {key: serialize_value(value) for key, value in invoice_row.items()}
        invoice["fiscal_number"] = self._format_fiscal_number(str(invoice.get("document_type") or "FACTURA"), int(invoice.get("point_of_sale") or 1), int(invoice.get("invoice_number") or 0))
        items = [{key: serialize_value(value) for key, value in row.items()} for row in item_rows]
        current_discount = sum(int(item.get("discount") or 0) for item in items)
        invoice_discount = int(invoice.get("discount_total") or current_discount)
        delta = invoice_discount - current_discount
        allocations = self._allocate_integer_amount(delta, [int(item.get("gross") or 0) for item in items])
        for item, allocation in zip(items, allocations):
            effective_discount = int(item.get("discount") or 0) + allocation
            item["effective_discount"] = effective_discount
            item["effective_total"] = int(item.get("gross") or 0) - effective_discount
        for item in items:
            if item.get("iva_rate") is None and item.get("product_iva_rate") is not None:
                item["iva_rate"] = item["product_iva_rate"]
        invoice["items"] = items
        return cast(InvoiceDetailData, invoice)

    def save_invoice(
        self,
        order: OrderData,
        profile: CustomerProfileData,
        snapshot: InvoiceSnapshotData,
        filename: str,
        xlsx_bytes: bytes,
        *,
        update_customer: bool = True,
        batch_id: int | None = None,
        split_kind: str | None = None,
        split_percentage: float | None = None,
        fiscal_status: str | None = None,
    ) -> int:
        created_at = utc_now()
        order_date = datetime.strptime(order["date"], "%Y-%m-%d").date()
        _mode, footer_discounts, line_discounts_by_format = canonicalize_discount_config(
            profile.get("footer_discounts", []),
            profile.get("line_discounts_by_format", {}),
        )
        invoice_payload = {
            "customer_id": None,
            "transport_id": None,
            "price_list_id": order.get("price_list_id"),
            "batch_id": batch_id,
            "legacy_key": f"invoice:{int(created_at.timestamp())}:{order['client_name']}",
            "document_type": "FACTURA",
            "point_of_sale": 1,
            "invoice_number": 1,
            "client_name": order["client_name"],
            "declared": bool(order.get("declared", False)),
            "split_kind": split_kind,
            "split_percentage": split_percentage,
            "fiscal_status": fiscal_status or ("draft" if bool(order.get("declared", False)) else "internal"),
            "price_list_name": str(order.get("price_list_name") or ""),
            "price_list_effective_date": None,
            "customer_cuit": str(profile.get("cuit", "") or ""),
            "customer_address": str(profile.get("address", "") or ""),
            "customer_business_name": str(profile.get("business_name", "") or ""),
            "customer_email": str(profile.get("email", "") or ""),
            "order_date": order_date,
            "secondary_line": order.get("secondary_line") or profile.get("secondary_line") or "",
            "transport": order.get("transport") or profile.get("transport") or "",
            "notes": order.get("notes") or profile.get("notes") or [],
            "footer_discounts": footer_discounts,
            "line_discounts_by_format": line_discounts_by_format,
            "total_bultos": float(snapshot["summary"]["total_bultos"]),
            "gross_total": int(snapshot["summary"]["gross_total"]),
            "discount_total": int(snapshot["summary"]["discount_total"]),
            "final_total": int(snapshot["summary"]["final_total"]),
            "output_filename": filename,
            "xlsx_data": xlsx_bytes,
            "xlsx_size": len(xlsx_bytes),
            "created_at": created_at,
        }
        item_payloads = []
        for index, item in enumerate(snapshot["rows"], start=1):
            item_payload = {
                    "line_number": index,
                    "product_id": item.get("product_id"),
                    "offering_id": item.get("offering_id"),
                    "product_name": str(item.get("product_name") or ""),
                    "offering_label": str(item.get("offering_label") or ""),
                    "offering_net_weight_kg": float(item.get("offering_net_weight_kg") or 0),
                    "line_type": str(item.get("line_type") or "sale"),
                    "discount_rate": float(item.get("discount_rate") or 0),
                    "label": item["label"],
                    "quantity": float(item["quantity"]),
                    "unit_price": int(item["unit_price"]),
                    "gross": int(item["gross"]),
                    "discount": int(item["discount"]),
                    "total": int(item["total"]),
                }
            item_payload.update(self._fiscal_item_values(cast(dict[str, object], item)))
            item_payloads.append(item_payload)
        with self.engine.begin() as connection:
            document_type, point_of_sale = self._fiscal_scope()
            invoice_payload["document_type"] = document_type
            invoice_payload["point_of_sale"] = point_of_sale
            invoice_payload["invoice_number"] = self._next_fiscal_number(
                connection=connection,
                document_type=document_type,
                point_of_sale=point_of_sale,
                now=created_at,
            )
            if invoice_payload["price_list_id"]:
                price_list_row = connection.execute(
                    select(self.price_lists.c.name, self.price_lists.c.uploaded_at).where(self.price_lists.c.id == invoice_payload["price_list_id"])
                ).mappings().first()
                if price_list_row:
                    invoice_payload["price_list_name"] = str(price_list_row["name"] or invoice_payload["price_list_name"] or "")
                    invoice_payload["price_list_effective_date"] = price_list_row["uploaded_at"]
            transport_name = order.get("transport") or profile.get("transport") or ""
            transport_id = self._resolve_transport_id(connection=connection, transport_name=transport_name, now=created_at)
            customer_id = None
            if update_customer:
                customer_id = self._upsert_customer(
                    {
                        "id": profile.get("id"),
                        "name": order["client_name"],
                        "cuit": profile.get("cuit", ""),
                        "address": profile.get("address", ""),
                        "business_name": profile.get("business_name", ""),
                        "email": profile.get("email", ""),
                        "secondary_line": order.get("secondary_line") or profile.get("secondary_line") or "",
                        "notes": order.get("notes") or profile.get("notes") or [],
                        "footer_discounts": invoice_payload["footer_discounts"],
                        "line_discounts_by_format": invoice_payload["line_discounts_by_format"],
                        "automatic_bonus_rules": profile.get("automatic_bonus_rules", []),
                        "automatic_bonus_disables_line_discount": bool(profile.get("automatic_bonus_disables_line_discount", False)),
                        "source_count": int(profile.get("source_count", 0)),
                        "transport_id": transport_id,
                        "created_at": created_at,
                        "updated_at": created_at,
                    },
                    connection=connection,
                    now=created_at,
                )
            elif profile.get("id") is not None:
                customer_id = connection.execute(
                    select(self.customers.c.id).where(self.customers.c.id == profile.get("id"))
                ).scalar_one_or_none()
                if customer_id is None:
                    raise ValueError("Cliente no encontrado")
            invoice_payload["customer_id"] = int(customer_id) if customer_id is not None else None
            invoice_payload["transport_id"] = transport_id
            invoice_id = connection.execute(self.invoices.insert().values(**invoice_payload).returning(self.invoices.c.id)).scalar_one()
            if item_payloads:
                for item_payload in item_payloads:
                    item_payload["invoice_id"] = invoice_id
                connection.execute(self.invoice_items.insert(), item_payloads)
                breakdown: dict[Decimal, dict[str, Decimal]] = {}
                for item_payload in item_payloads:
                    iva_rate = item_payload.get("iva_rate")
                    if iva_rate is None:
                        continue
                    rate = Decimal(str(iva_rate))
                    current = breakdown.setdefault(rate, {"base_amount": Decimal("0"), "iva_amount": Decimal("0")})
                    current["base_amount"] += Decimal(str(item_payload.get("net_amount") or 0))
                    current["iva_amount"] += Decimal(str(item_payload.get("iva_amount") or 0))
                if breakdown:
                    connection.execute(
                        self.invoice_tax_breakdown.insert(),
                        [
                            {
                                "invoice_id": invoice_id,
                                "iva_rate": rate,
                                "arca_iva_id": self._arca_iva_id(rate),
                                "base_amount": values["base_amount"],
                                "iva_amount": values["iva_amount"],
                                "created_at": created_at,
                            }
                            for rate, values in breakdown.items()
                        ],
                    )
        return invoice_id

    def save_invoice_batch(
        self,
        *,
        batch: dict[str, object],
        invoices: list[dict[str, object]],
        update_customer: bool = True,
        replace_batch_id: int | None = None,
    ) -> tuple[int, list[int]]:
        created_at = utc_now()
        order_date = datetime.strptime(str(batch["order_date"]), "%Y-%m-%d").date()
        invoice_ids: list[int] = []

        with self.engine.begin() as connection:
            if replace_batch_id is not None:
                existing = connection.execute(
                    select(self.invoices.c.id, self.invoices.c.fiscal_status)
                    .where(self.invoices.c.batch_id == replace_batch_id)
                    .with_for_update()
                ).mappings().all()
                if any(str(row["fiscal_status"] or "") == "authorized" for row in existing):
                    raise ValueError("No se puede editar un batch split con parte fiscal autorizada")
                connection.execute(self.invoices.delete().where(self.invoices.c.batch_id == replace_batch_id))
                connection.execute(self.invoice_batches.delete().where(self.invoice_batches.c.id == replace_batch_id))

            transport_name = str(batch.get("transport") or "")
            transport_id = self._resolve_transport_id(connection=connection, transport_name=transport_name, now=created_at)
            customer_id = None
            profile = cast(CustomerProfileData, batch["profile"])
            if update_customer:
                customer_id = self._upsert_customer(
                    {
                        "id": profile.get("id"),
                        "name": str(batch["client_name"]),
                        "cuit": profile.get("cuit", ""),
                        "address": profile.get("address", ""),
                        "business_name": profile.get("business_name", ""),
                        "email": profile.get("email", ""),
                        "secondary_line": batch.get("secondary_line") or profile.get("secondary_line") or "",
                        "notes": batch.get("notes") or profile.get("notes") or [],
                        "footer_discounts": profile.get("footer_discounts", []),
                        "line_discounts_by_format": profile.get("line_discounts_by_format", {}),
                        "automatic_bonus_rules": profile.get("automatic_bonus_rules", []),
                        "automatic_bonus_disables_line_discount": bool(profile.get("automatic_bonus_disables_line_discount", False)),
                        "source_count": int(profile.get("source_count", 0)),
                        "transport_id": transport_id,
                        "created_at": created_at,
                        "updated_at": created_at,
                    },
                    connection=connection,
                    now=created_at,
                )
            elif profile.get("id") is not None:
                customer_id = connection.execute(select(self.customers.c.id).where(self.customers.c.id == profile.get("id"))).scalar_one_or_none()
                if customer_id is None:
                    raise ValueError("Cliente no encontrado")

            batch_id = int(
                connection.execute(
                    self.invoice_batches.insert()
                    .values(
                        customer_id=int(customer_id) if customer_id is not None else None,
                        client_name=str(batch["client_name"]),
                        order_date=order_date,
                        billing_mode=str(batch["billing_mode"]),
                        declared_percentage=batch.get("declared_percentage"),
                        internal_percentage=batch.get("internal_percentage"),
                        internal_price_list_id=batch.get("internal_price_list_id"),
                        fiscal_price_list_id=batch.get("fiscal_price_list_id"),
                        created_by_user_id=None,
                        created_at=created_at,
                    )
                    .returning(self.invoice_batches.c.id)
                ).scalar_one()
            )

            document_type, point_of_sale = self._fiscal_scope()
            for doc in invoices:
                order = cast(OrderData, doc["order"])
                snapshot = cast(InvoiceSnapshotData, doc["snapshot"])
                _mode, footer_discounts, line_discounts_by_format = canonicalize_discount_config(
                    profile.get("footer_discounts", []),
                    profile.get("line_discounts_by_format", {}),
                )
                price_list_id = order.get("price_list_id")
                price_list_name = ""
                price_list_effective_date = None
                if price_list_id:
                    price_list_row = connection.execute(select(self.price_lists.c.name, self.price_lists.c.uploaded_at).where(self.price_lists.c.id == price_list_id)).mappings().first()
                    if price_list_row:
                        price_list_name = str(price_list_row["name"] or "")
                        price_list_effective_date = price_list_row["uploaded_at"]
                invoice_payload = {
                    "customer_id": int(customer_id) if customer_id is not None else None,
                    "transport_id": transport_id,
                    "price_list_id": price_list_id,
                    "batch_id": batch_id,
                    "legacy_key": f"invoice:{int(created_at.timestamp())}:{order['client_name']}:{doc.get('split_kind')}",
                    "document_type": document_type,
                    "point_of_sale": point_of_sale,
                    "invoice_number": self._next_fiscal_number(connection=connection, document_type=document_type, point_of_sale=point_of_sale, now=created_at),
                    "client_name": order["client_name"],
                    "declared": bool(order.get("declared", False)),
                    "split_kind": doc.get("split_kind"),
                    "split_percentage": doc.get("split_percentage"),
                    "fiscal_status": str(doc.get("fiscal_status") or ("draft" if order.get("declared") else "internal")),
                    "price_list_name": price_list_name,
                    "price_list_effective_date": price_list_effective_date,
                    "customer_cuit": str(profile.get("cuit", "") or ""),
                    "customer_address": str(profile.get("address", "") or ""),
                    "customer_business_name": str(profile.get("business_name", "") or ""),
                    "customer_email": str(profile.get("email", "") or ""),
                    "order_date": order_date,
                    "secondary_line": order.get("secondary_line") or profile.get("secondary_line") or "",
                    "transport": order.get("transport") or profile.get("transport") or "",
                    "notes": order.get("notes") or profile.get("notes") or [],
                    "footer_discounts": footer_discounts,
                    "line_discounts_by_format": line_discounts_by_format,
                    "total_bultos": float(snapshot["summary"]["total_bultos"]),
                    "gross_total": int(snapshot["summary"]["gross_total"]),
                    "discount_total": int(snapshot["summary"]["discount_total"]),
                    "final_total": int(snapshot["summary"]["final_total"]),
                    "output_filename": str(doc["filename"]),
                    "xlsx_data": doc["xlsx_bytes"],
                    "xlsx_size": len(cast(bytes, doc["xlsx_bytes"])),
                    "created_at": created_at,
                }
                invoice_id = int(connection.execute(self.invoices.insert().values(**invoice_payload).returning(self.invoices.c.id)).scalar_one())
                invoice_ids.append(invoice_id)
                item_payloads = []
                for index, item in enumerate(snapshot["rows"], start=1):
                    item_payload = {
                        "invoice_id": invoice_id,
                        "line_number": index,
                        "product_id": item.get("product_id"),
                        "offering_id": item.get("offering_id"),
                        "product_name": str(item.get("product_name") or ""),
                        "offering_label": str(item.get("offering_label") or ""),
                        "offering_net_weight_kg": float(item.get("offering_net_weight_kg") or 0),
                        "line_type": str(item.get("line_type") or "sale"),
                        "discount_rate": float(item.get("discount_rate") or 0),
                        "label": item["label"],
                        "quantity": float(item["quantity"]),
                        "unit_price": int(item["unit_price"]),
                        "gross": int(item["gross"]),
                        "discount": int(item["discount"]),
                        "total": int(item["total"]),
                    }
                    item_payload.update(self._fiscal_item_values(cast(dict[str, object], item)))
                    item_payloads.append(item_payload)
                if item_payloads:
                    connection.execute(self.invoice_items.insert(), item_payloads)
                    breakdown: dict[Decimal, dict[str, Decimal]] = {}
                    for item_payload in item_payloads:
                        iva_rate = item_payload.get("iva_rate")
                        if iva_rate is None:
                            continue
                        rate = Decimal(str(iva_rate))
                        current = breakdown.setdefault(rate, {"base_amount": Decimal("0"), "iva_amount": Decimal("0")})
                        current["base_amount"] += Decimal(str(item_payload.get("net_amount") or 0))
                        current["iva_amount"] += Decimal(str(item_payload.get("iva_amount") or 0))
                    if breakdown:
                        connection.execute(
                            self.invoice_tax_breakdown.insert(),
                            [
                                {
                                    "invoice_id": invoice_id,
                                    "iva_rate": rate,
                                    "arca_iva_id": self._arca_iva_id(rate),
                                    "base_amount": values["base_amount"],
                                    "iva_amount": values["iva_amount"],
                                    "created_at": created_at,
                                }
                                for rate, values in breakdown.items()
                            ],
                        )
        return batch_id, invoice_ids

    def list_batch_invoice_statuses(self, batch_id: int) -> list[dict[str, object]]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(self.invoices.c.id.label("invoice_id"), self.invoices.c.split_kind, self.invoices.c.fiscal_status)
                .where(self.invoices.c.batch_id == batch_id)
                .order_by(self.invoices.c.id)
            ).mappings().all()
        return [{key: serialize_value(value) for key, value in row.items()} for row in rows]

    def get_invoice_tax_breakdown(self, invoice_id: int) -> list[dict[str, object]]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(
                    self.invoice_tax_breakdown.c.iva_rate,
                    self.invoice_tax_breakdown.c.arca_iva_id,
                    self.invoice_tax_breakdown.c.base_amount,
                    self.invoice_tax_breakdown.c.iva_amount,
                )
                .where(self.invoice_tax_breakdown.c.invoice_id == invoice_id)
                .order_by(self.invoice_tax_breakdown.c.iva_rate)
            ).mappings().all()
        return [{key: serialize_value(value) for key, value in row.items()} for row in rows]

    def create_arca_request(
        self,
        *,
        invoice_id: int,
        operation: str,
        environment: str,
        sanitized_request: dict[str, object],
        status: str = "pending",
        sanitized_response: dict[str, object] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> int:
        created_at = utc_now()
        encoded_request = json.dumps(sanitized_request, sort_keys=True, default=str).encode("utf-8")
        request_hash = hashlib.sha256(encoded_request).hexdigest()
        with self.engine.begin() as connection:
            arca_request_id = int(
                connection.execute(
                    self.arca_requests.insert()
                    .values(
                        invoice_id=invoice_id,
                        operation=operation,
                        environment=environment,
                        request_hash=request_hash,
                        sanitized_request=sanitized_request,
                        sanitized_response=sanitized_response,
                        status=status,
                        error_code=error_code,
                        error_message=error_message,
                        created_at=created_at,
                    )
                    .returning(self.arca_requests.c.id)
                ).scalar_one()
            )
            connection.execute(update(self.invoices).where(self.invoices.c.id == invoice_id).values(arca_request_id=str(arca_request_id)))
        return arca_request_id

    def update_arca_request(
        self,
        arca_request_id: int,
        *,
        status: str,
        sanitized_response: dict[str, object] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                update(self.arca_requests)
                .where(self.arca_requests.c.id == arca_request_id)
                .values(status=status, sanitized_response=sanitized_response, error_code=error_code, error_message=error_message)
            )

    def update_invoice_arca_status(
        self,
        invoice_id: int,
        *,
        fiscal_status: str,
        arca_environment: str,
        arca_cuit_emisor: str,
        arca_cbte_tipo: int,
        arca_concepto: int,
        arca_doc_tipo: int,
        arca_doc_nro: str,
        arca_point_of_sale: int,
        arca_request_id: int,
        arca_invoice_number: int | None = None,
        arca_cae: str | None = None,
        arca_cae_expires_at: date | None = None,
        arca_result: str | None = None,
        arca_observations: object | None = None,
        arca_error_code: str | None = None,
        arca_error_message: str | None = None,
    ) -> None:
        now = utc_now()
        values = {
            "fiscal_status": fiscal_status,
            "fiscal_locked_at": now if fiscal_status == "authorized" else None,
            "fiscal_authorized_at": now if fiscal_status == "authorized" else None,
            "arca_environment": arca_environment,
            "arca_cuit_emisor": arca_cuit_emisor,
            "arca_cbte_tipo": arca_cbte_tipo,
            "arca_concepto": arca_concepto,
            "arca_doc_tipo": arca_doc_tipo,
            "arca_doc_nro": arca_doc_nro,
            "arca_point_of_sale": arca_point_of_sale,
            "arca_invoice_number": arca_invoice_number,
            "arca_cae": arca_cae,
            "arca_cae_expires_at": arca_cae_expires_at,
            "arca_result": arca_result,
            "arca_observations": arca_observations,
            "arca_error_code": arca_error_code,
            "arca_error_message": arca_error_message,
            "arca_request_id": str(arca_request_id),
        }
        with self.engine.begin() as connection:
            connection.execute(update(self.invoices).where(self.invoices.c.id == invoice_id).values(**values))

    def update_invoice(
        self,
        invoice_id: int,
        order: OrderData,
        profile: CustomerProfileData,
        snapshot: InvoiceSnapshotData,
        filename: str,
        xlsx_bytes: bytes,
    ) -> int:
        updated_at = utc_now()
        order_date = datetime.strptime(order["date"], "%Y-%m-%d").date()
        _mode, footer_discounts, line_discounts_by_format = canonicalize_discount_config(
            profile.get("footer_discounts", []),
            profile.get("line_discounts_by_format", {}),
        )

        with self.engine.begin() as connection:
            existing_invoice = connection.execute(
                select(self.invoices).where(self.invoices.c.id == invoice_id)
            ).mappings().first()
            if not existing_invoice:
                raise ValueError("Factura no encontrada")

            transport_name = order.get("transport") or profile.get("transport") or ""
            price_list_name = str(order.get("price_list_name") or "")
            price_list_effective_date = None
            if order.get("price_list_id"):
                price_list_row = connection.execute(
                    select(self.price_lists.c.name, self.price_lists.c.uploaded_at).where(self.price_lists.c.id == order.get("price_list_id"))
                ).mappings().first()
                if price_list_row:
                    price_list_name = str(price_list_row["name"] or price_list_name)
                    price_list_effective_date = price_list_row["uploaded_at"]
            transport_id = self._resolve_transport_id(connection=connection, transport_name=transport_name, now=updated_at)
            customer_id = self._upsert_customer(
                {
                    "id": profile.get("id") or existing_invoice.get("customer_id"),
                    "name": order["client_name"],
                    "cuit": profile.get("cuit", ""),
                    "address": profile.get("address", ""),
                    "business_name": profile.get("business_name", ""),
                    "email": profile.get("email", ""),
                    "secondary_line": order.get("secondary_line") or profile.get("secondary_line") or "",
                    "notes": order.get("notes") or profile.get("notes") or [],
                    "footer_discounts": footer_discounts,
                    "line_discounts_by_format": line_discounts_by_format,
                    "automatic_bonus_rules": profile.get("automatic_bonus_rules", []),
                    "automatic_bonus_disables_line_discount": bool(profile.get("automatic_bonus_disables_line_discount", False)),
                    "source_count": int(profile.get("source_count", 0)),
                    "transport_id": transport_id,
                    "created_at": existing_invoice.get("created_at") or updated_at,
                    "updated_at": updated_at,
                },
                connection=connection,
                now=updated_at,
            )

            connection.execute(
                update(self.invoices)
                .where(self.invoices.c.id == invoice_id)
                .values(
                    customer_id=customer_id,
                    transport_id=transport_id,
                    price_list_id=order.get("price_list_id"),
                    client_name=order["client_name"],
                    declared=bool(order.get("declared", False)),
                    fiscal_status=str(existing_invoice.get("fiscal_status") or ("draft" if bool(order.get("declared", False)) else "internal")),
                    price_list_name=price_list_name,
                    price_list_effective_date=price_list_effective_date,
                    customer_cuit=str(profile.get("cuit", "") or ""),
                    customer_address=str(profile.get("address", "") or ""),
                    customer_business_name=str(profile.get("business_name", "") or ""),
                    customer_email=str(profile.get("email", "") or ""),
                    order_date=order_date,
                    secondary_line=order.get("secondary_line") or profile.get("secondary_line") or "",
                    transport=transport_name,
                    notes=order.get("notes") or profile.get("notes") or [],
                    footer_discounts=footer_discounts,
                    line_discounts_by_format=line_discounts_by_format,
                    total_bultos=float(snapshot["summary"]["total_bultos"]),
                    gross_total=int(snapshot["summary"]["gross_total"]),
                    discount_total=int(snapshot["summary"]["discount_total"]),
                    final_total=int(snapshot["summary"]["final_total"]),
                    output_filename=filename,
                    xlsx_data=xlsx_bytes,
                    xlsx_size=len(xlsx_bytes),
                )
            )

            connection.execute(
                self.invoice_items.delete().where(self.invoice_items.c.invoice_id == invoice_id)
            )

            item_payloads = []
            for index, item in enumerate(snapshot["rows"], start=1):
                item_payloads.append(
                    {
                        "invoice_id": invoice_id,
                        "line_number": index,
                        "product_id": item.get("product_id"),
                        "offering_id": item.get("offering_id"),
                        "product_name": str(item.get("product_name") or ""),
                        "offering_label": str(item.get("offering_label") or ""),
                        "offering_net_weight_kg": float(item.get("offering_net_weight_kg") or 0),
                        "line_type": str(item.get("line_type") or "sale"),
                        "discount_rate": float(item.get("discount_rate") or 0),
                        "label": item["label"],
                        "quantity": float(item["quantity"]),
                        "unit_price": int(item["unit_price"]),
                        "gross": int(item["gross"]),
                        "discount": int(item["discount"]),
                        "total": int(item["total"]),
                    }
                )
            if item_payloads:
                connection.execute(self.invoice_items.insert(), item_payloads)

        return invoice_id

    def delete_invoice(self, invoice_id: int) -> None:
        with self.engine.begin() as connection:
            existing_invoice = connection.execute(
                select(self.invoices.c.id, self.invoices.c.batch_id, self.invoices.c.fiscal_status).where(self.invoices.c.id == invoice_id)
            ).mappings().first()
            if not existing_invoice:
                raise ValueError("Factura no encontrada")
            if str(existing_invoice["fiscal_status"] or "") == "authorized":
                raise ValueError("No se puede eliminar un comprobante fiscal autorizado")
            batch_id = existing_invoice.get("batch_id")
            if batch_id is not None:
                batch_rows = connection.execute(
                    select(self.invoices.c.fiscal_status).where(self.invoices.c.batch_id == batch_id).with_for_update()
                ).mappings().all()
                if any(str(row["fiscal_status"] or "") == "authorized" for row in batch_rows):
                    raise ValueError("No se puede eliminar un batch split con parte fiscal autorizada")
                connection.execute(self.invoices.delete().where(self.invoices.c.batch_id == batch_id))
                connection.execute(self.invoice_batches.delete().where(self.invoice_batches.c.id == batch_id))
                return
            result = connection.execute(
                self.invoices.delete().where(self.invoices.c.id == invoice_id)
            )
            if result.rowcount == 0:
                raise ValueError("Factura no encontrada")

    def get_invoice_file(self, invoice_id: int) -> InvoiceFileData | None:
        with self.engine.connect() as connection:
            row = connection.execute(
                select(self.invoices.c.output_filename, self.invoices.c.xlsx_data, self.invoices.c.xlsx_size).where(self.invoices.c.id == invoice_id)
            ).mappings().first()
        if not row:
            return None
        payload: InvoiceFileData = cast(InvoiceFileData, {key: serialize_value(value) for key, value in row.items()})
        return payload

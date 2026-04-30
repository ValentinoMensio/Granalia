from __future__ import annotations

from datetime import datetime
from typing import cast

from sqlalchemy import select, update
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
    price_lists: Table

    def list_invoices(self, limit: int = 50) -> list[InvoiceListItemData]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(
                    self.invoices.c.id.label("invoice_id"),
                    self.invoices.c.customer_id,
                    self.invoices.c.transport_id,
                    self.invoices.c.client_name,
                    self.invoices.c.transport,
                    self.invoices.c.order_date,
                    self.invoices.c.price_list_id,
                    self.invoices.c.price_list_name,
                    self.invoices.c.declared,
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
            ).mappings().all()
        payload: list[InvoiceListItemData] = cast(list[InvoiceListItemData], [{key: serialize_value(value) for key, value in row.items()} for row in rows])
        return payload

    def list_invoice_item_stats(self) -> list[dict[str, object]]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(
                    self.invoices.c.id.label("invoice_id"),
                    self.invoices.c.customer_id,
                    self.invoices.c.transport_id,
                    self.invoices.c.client_name,
                    self.invoices.c.transport,
                    self.invoices.c.order_date,
                    self.invoices.c.gross_total.label("invoice_gross_total"),
                    self.invoices.c.discount_total.label("invoice_discount_total"),
                    self.invoices.c.final_total.label("invoice_final_total"),
                    self.invoice_items.c.product_id,
                    self.invoice_items.c.offering_id,
                    self.invoice_items.c.label,
                    self.invoice_items.c.quantity,
                    self.invoice_items.c.unit_price,
                    self.invoice_items.c.gross,
                    self.invoice_items.c.discount,
                    self.invoice_items.c.total,
                    self.products.c.name.label("product_name"),
                    self.product_offerings.c.label.label("offering_label"),
                    self.product_offerings.c.net_weight_kg.label("offering_net_weight_kg"),
                )
                .select_from(
                    self.invoice_items
                    .join(self.invoices, self.invoice_items.c.invoice_id == self.invoices.c.id)
                    .outerjoin(self.products, self.invoice_items.c.product_id == self.products.c.id)
                    .outerjoin(self.product_offerings, self.invoice_items.c.offering_id == self.product_offerings.c.id)
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
                    self.invoices.c.customer_id,
                    self.invoices.c.transport_id,
                    self.invoices.c.legacy_key,
                    self.invoices.c.client_name,
                    self.invoices.c.order_date,
                    self.invoices.c.price_list_id,
                    self.invoices.c.price_list_name,
                    self.invoices.c.declared,
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
                    self.customers.c.name.label("customer_name"),
                    self.customers.c.cuit.label("customer_cuit"),
                    self.customers.c.address.label("customer_address"),
                    self.customers.c.email.label("customer_email"),
                    self.transports.c.name.label("transport_name"),
                )
                .select_from(
                    self.invoices
                    .outerjoin(self.customers, self.invoices.c.customer_id == self.customers.c.id)
                    .outerjoin(self.transports, self.invoices.c.transport_id == self.transports.c.transport_id)
                )
                .where(self.invoices.c.id == invoice_id)
            ).mappings().first()
            if not invoice_row:
                return None

            item_rows = connection.execute(
                select(
                    self.invoice_items,
                    self.products.c.name.label("product_name"),
                    self.product_offerings.c.label.label("offering_label"),
                    self.product_offerings.c.net_weight_kg.label("offering_net_weight_kg"),
                )
                .select_from(
                    self.invoice_items
                    .outerjoin(self.products, self.invoice_items.c.product_id == self.products.c.id)
                    .outerjoin(self.product_offerings, self.invoice_items.c.offering_id == self.product_offerings.c.id)
                )
                .where(self.invoice_items.c.invoice_id == invoice_id)
                .order_by(self.invoice_items.c.line_number)
            ).mappings().all()

        invoice = {key: serialize_value(value) for key, value in invoice_row.items()}
        items = [{key: serialize_value(value) for key, value in row.items()} for row in item_rows]
        invoice["items"] = items
        return cast(InvoiceDetailData, invoice)

    def save_invoice(
        self,
        order: OrderData,
        profile: CustomerProfileData,
        snapshot: InvoiceSnapshotData,
        filename: str,
        xlsx_bytes: bytes,
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
            "legacy_key": f"invoice:{int(created_at.timestamp())}:{order['client_name']}",
            "client_name": order["client_name"],
            "declared": bool(order.get("declared", False)),
            "price_list_name": str(order.get("price_list_name") or ""),
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
            item_payloads.append(
                {
                    "line_number": index,
                    "product_id": item.get("product_id"),
                    "offering_id": item.get("offering_id"),
                    "label": item["label"],
                    "quantity": float(item["quantity"]),
                    "unit_price": int(item["unit_price"]),
                    "gross": int(item["gross"]),
                    "discount": int(item["discount"]),
                    "total": int(item["total"]),
                }
            )
        with self.engine.begin() as connection:
            if invoice_payload["price_list_id"]:
                price_list_row = connection.execute(select(self.price_lists.c.name).where(self.price_lists.c.id == invoice_payload["price_list_id"])).scalar_one_or_none()
                invoice_payload["price_list_name"] = str(price_list_row or invoice_payload["price_list_name"] or "")
            transport_name = order.get("transport") or profile.get("transport") or ""
            transport_id = self._resolve_transport_id(connection=connection, transport_name=transport_name, now=created_at)
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
            customer_row = connection.execute(select(self.customers).where(self.customers.c.id == customer_id)).mappings().first()
            invoice_payload["customer_id"] = customer_row["id"] if customer_row else None
            invoice_payload["transport_id"] = transport_id
            invoice_id = connection.execute(self.invoices.insert().values(**invoice_payload).returning(self.invoices.c.id)).scalar_one()
            if item_payloads:
                for item_payload in item_payloads:
                    item_payload["invoice_id"] = invoice_id
                connection.execute(self.invoice_items.insert(), item_payloads)
        return invoice_id

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
            if order.get("price_list_id"):
                price_list_row = connection.execute(select(self.price_lists.c.name).where(self.price_lists.c.id == order.get("price_list_id"))).scalar_one_or_none()
                price_list_name = str(price_list_row or price_list_name)
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
                    price_list_name=price_list_name,
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

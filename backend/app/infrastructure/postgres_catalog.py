from __future__ import annotations

import re

from sqlalchemy import select, update
from sqlalchemy.engine import Engine
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.sql.schema import Table
from typing import cast

from ..core.utils import canonicalize_discount_config
from ..types import CatalogOfferingData, CatalogProductData, PriceListMetaData
from .postgres_protocol import PostgresRepositoryProtocol
from .postgres_utils import serialize_value, utc_now


def _net_weight_kg_for_label(label: str) -> float:
    text = str(label or "").lower().replace(" ", "")
    pack_match = re.search(r"(\d+)x(\d+(?:[.,]\d+)?)(kg|gr|g)?", text)
    if pack_match:
        units = float(pack_match.group(1) or 0)
        size = float((pack_match.group(2) or "0").replace(",", "."))
        unit = pack_match.group(3) or "gr"
        return units * (size if unit == "kg" else size / 1000)

    bag_match = re.search(r"x(\d+(?:[.,]\d+)?)kg", text)
    if bag_match:
        return float((bag_match.group(1) or "0").replace(",", "."))

    return 0


def _offering_net_weight(offering: CatalogOfferingData | dict[str, object], label: str, existing: dict[str, object] | None = None) -> float:
    explicit = float(offering.get("net_weight_kg") or 0)
    if explicit > 0:
        return explicit
    previous = float(existing.get("net_weight_kg") or 0) if existing else 0
    if previous > 0:
        return previous
    return _net_weight_kg_for_label(label)


class PostgresCatalogMixin(PostgresRepositoryProtocol):
    engine: Engine
    products: Table
    product_offerings: Table
    catalogs: Table
    customers: Table
    price_lists: Table

    def _catalog_snapshot(self, *, connection, active_only: bool = True) -> list[CatalogProductData]:
        product_query = select(self.products).order_by(self.products.c.name)
        offering_query = select(self.product_offerings).order_by(self.product_offerings.c.product_id, self.product_offerings.c.position)
        if active_only:
            product_query = product_query.where(self.products.c.active.is_(True))
            offering_query = offering_query.where(self.product_offerings.c.active.is_(True))

        product_rows = connection.execute(product_query).mappings().all()
        if not product_rows:
            return []

        offering_rows = connection.execute(offering_query).mappings().all()
        offerings_by_product: dict[int, list[CatalogOfferingData]] = {}
        for row in offering_rows:
            offerings_by_product.setdefault(row["product_id"], []).append(
                {
                    "id": row["id"],
                    "label": row["label"],
                    "price": int(row["price"]),
                    "net_weight_kg": float(row.get("net_weight_kg") or 0),
                }
            )

        return [
            {
                "id": row["id"],
                "name": row["name"],
                "aliases": row["aliases"],
                "iva_rate": float(row["iva_rate"]) if row.get("iva_rate") is not None else None,
                "offerings": offerings_by_product.get(row["id"], []),
            }
            for row in product_rows
        ]

    def _refresh_active_catalog_snapshot(self, *, connection, now) -> None:
        connection.execute(
            update(self.catalogs)
            .where(self.catalogs.c.active.is_(True))
            .values(catalog=self._catalog_snapshot(connection=connection), updated_at=now)
        )

    def _sync_catalog_tables(self, catalog: list[CatalogProductData], *, connection, now) -> None:
        active_product_db_ids: set[int] = set()
        active_offering_db_ids: set[int] = set()

        connection.execute(update(self.products).values(active=False, updated_at=now))
        connection.execute(update(self.product_offerings).values(active=False, updated_at=now))

        for product in catalog:
            product_name = product["name"]
            product_id = product.get("id") if isinstance(product.get("id"), int) else None
            existing_product = connection.execute(
                select(self.products).where(self.products.c.id == product_id)
                if product_id is not None
                else select(self.products).where(self.products.c.name == product_name)
            ).mappings().first()
            if not existing_product and product_id is not None:
                existing_product = connection.execute(
                    select(self.products).where(self.products.c.name == product_name)
                ).mappings().first()
            if existing_product:
                product_db_id = existing_product["id"]
                connection.execute(
                    update(self.products)
                    .where(self.products.c.id == product_db_id)
                    .values(
                        name=product_name,
                        aliases=product.get("aliases", []),
                        iva_rate=product.get("iva_rate"),
                        active=True,
                        updated_at=now,
                    )
                )
            else:
                product_db_id = connection.execute(
                    insert(self.products)
                    .values(
                        name=product_name,
                        aliases=product.get("aliases", []),
                        iva_rate=product.get("iva_rate"),
                        active=True,
                        created_at=now,
                        updated_at=now,
                    )
                    .returning(self.products.c.id)
                ).scalar_one()
            active_product_db_ids.add(product_db_id)

            for position, offering in enumerate(product.get("offerings", []), start=1):
                offering_label = offering["label"]
                offering_id = offering.get("id") if isinstance(offering.get("id"), int) else None
                if offering_id:
                    existing_by_id = connection.execute(
                        select(self.product_offerings).where(self.product_offerings.c.id == offering_id)
                    ).mappings().first()
                    if not existing_by_id or existing_by_id["product_id"] != product_db_id:
                        offering_id = None

                if offering_id:
                    duplicate = connection.execute(
                        select(self.product_offerings)
                        .where(
                            self.product_offerings.c.product_id == product_db_id,
                            self.product_offerings.c.label == offering_label,
                            self.product_offerings.c.id != offering_id,
                        )
                        .order_by(self.product_offerings.c.id)
                        .limit(1)
                    ).mappings().first()
                    if duplicate:
                        target_id = int(duplicate["id"])
                        connection.execute(
                            update(self.invoice_items)
                            .where(self.invoice_items.c.offering_id == offering_id)
                            .values(offering_id=target_id)
                        )
                        connection.execute(
                            update(self.product_offerings)
                            .where(self.product_offerings.c.id == target_id)
                            .values(
                                price=int(offering["price"]),
                                net_weight_kg=_offering_net_weight(offering, offering_label, duplicate),
                                position=position,
                                active=True,
                                updated_at=now,
                            )
                        )
                        connection.execute(self.product_offerings.delete().where(self.product_offerings.c.id == offering_id))
                        active_offering_db_ids.add(target_id)
                        continue

                    connection.execute(
                        update(self.product_offerings)
                        .where(self.product_offerings.c.id == offering_id)
                        .values(
                            product_id=product_db_id,
                            label=offering_label,
                            price=int(offering["price"]),
                            net_weight_kg=_offering_net_weight(offering, offering_label),
                            position=position,
                            active=True,
                            updated_at=now,
                        )
                    )
                    active_offering_db_ids.add(int(offering_id))
                else:
                    existing_offering = connection.execute(
                        select(self.product_offerings)
                        .where(
                            self.product_offerings.c.product_id == product_db_id,
                            self.product_offerings.c.label == offering_label,
                        )
                        .order_by(self.product_offerings.c.id)
                        .limit(1)
                    ).mappings().first()
                    if existing_offering:
                        existing_offering_id = int(existing_offering["id"])
                        connection.execute(
                            update(self.product_offerings)
                            .where(self.product_offerings.c.id == existing_offering_id)
                            .values(
                                price=int(offering["price"]),
                                net_weight_kg=_offering_net_weight(offering, offering_label, existing_offering),
                                position=position,
                                active=True,
                                updated_at=now,
                            )
                        )
                        active_offering_db_ids.add(existing_offering_id)
                    else:
                        inserted_id = connection.execute(
                            insert(self.product_offerings)
                            .values(
                                product_id=product_db_id,
                                label=offering_label,
                                price=int(offering["price"]),
                                net_weight_kg=_offering_net_weight(offering, offering_label),
                                position=position,
                                active=True,
                                created_at=now,
                                updated_at=now,
                            )
                            .returning(self.product_offerings.c.id)
                        ).scalar_one()
                        active_offering_db_ids.add(int(inserted_id))

        if active_product_db_ids:
            connection.execute(update(self.products).where(self.products.c.id.in_(active_product_db_ids)).values(active=True, updated_at=now))
        if active_offering_db_ids:
            connection.execute(update(self.product_offerings).where(self.product_offerings.c.id.in_(active_offering_db_ids)).values(active=True, updated_at=now))

    def get_active_catalog(self) -> list[CatalogProductData]:
        with self.engine.connect() as connection:
            catalog = self._catalog_snapshot(connection=connection)
        if not catalog:
            raise RuntimeError("No hay un catalogo activo en PostgreSQL")
        return catalog

    def save_product(self, payload: CatalogProductData) -> CatalogProductData:
        now = utc_now()
        product_id = payload.get("id")
        with self.engine.begin() as connection:
            if product_id is not None:
                existing = connection.execute(
                    select(self.products).where(self.products.c.id == product_id)
                ).mappings().first()
                if not existing:
                    raise ValueError("Producto no encontrado")
                connection.execute(
                    update(self.products)
                    .where(self.products.c.id == product_id)
                    .values(
                        name=payload["name"],
                        aliases=payload.get("aliases", []),
                        iva_rate=payload.get("iva_rate"),
                        active=True,
                        updated_at=now,
                    )
                )
                row = connection.execute(select(self.products).where(self.products.c.id == product_id)).mappings().first()
            else:
                existing = connection.execute(
                    select(self.products).where(self.products.c.name == payload["name"])
                ).mappings().first()
                if existing:
                    connection.execute(
                        update(self.products)
                        .where(self.products.c.id == existing["id"])
                        .values(
                            aliases=payload.get("aliases", []),
                            iva_rate=payload.get("iva_rate"),
                            active=True,
                            updated_at=now,
                        )
                    )
                    row = connection.execute(select(self.products).where(self.products.c.id == existing["id"])).mappings().first()
                else:
                    row = connection.execute(
                        insert(self.products)
                        .values(
                            name=payload["name"],
                            aliases=payload.get("aliases", []),
                            iva_rate=payload.get("iva_rate"),
                            active=True,
                            created_at=now,
                            updated_at=now,
                        )
                        .returning(self.products)
                    ).mappings().first()
            self._refresh_active_catalog_snapshot(connection=connection, now=now)
        return cast(CatalogProductData, {key: serialize_value(value) for key, value in row.items()})

    def save_product_offerings(self, product_id: int, offerings: list[CatalogOfferingData]) -> None:
        now = utc_now()
        with self.engine.begin() as connection:
            if not connection.execute(
                select(self.products.c.id).where(self.products.c.id == product_id)
            ).scalar_one_or_none():
                raise ValueError("Producto no encontrado")

            existing_rows = connection.execute(
                select(self.product_offerings).where(self.product_offerings.c.product_id == product_id)
            ).mappings().all()
            seen_ids: set[int] = set()

            for position, off in enumerate(offerings, start=1):
                offering_label = str(off.get("label") or "").strip()
                if not offering_label:
                    continue
                offering_id = off.get("id") if isinstance(off.get("id"), int) else None

                if offering_id is not None:
                    duplicate = connection.execute(
                        select(self.product_offerings)
                        .where(
                            self.product_offerings.c.product_id == product_id,
                            self.product_offerings.c.label == offering_label,
                            self.product_offerings.c.id != offering_id,
                        )
                        .order_by(self.product_offerings.c.id)
                        .limit(1)
                    ).mappings().first()
                    if duplicate:
                        target_id = int(duplicate["id"])
                        connection.execute(
                            update(self.invoice_items)
                            .where(self.invoice_items.c.offering_id == offering_id)
                            .values(offering_id=target_id)
                        )
                        connection.execute(
                            update(self.product_offerings)
                            .where(self.product_offerings.c.id == target_id)
                            .values(
                                price=int(off["price"]),
                                net_weight_kg=_offering_net_weight(off, offering_label, duplicate),
                                position=position,
                                active=True,
                                updated_at=now,
                            )
                        )
                        connection.execute(self.product_offerings.delete().where(self.product_offerings.c.id == offering_id))
                        seen_ids.add(target_id)
                        continue

                    connection.execute(
                        update(self.product_offerings)
                        .where(self.product_offerings.c.id == offering_id)
                        .values(
                            label=offering_label,
                            price=int(off["price"]),
                            net_weight_kg=_offering_net_weight(off, offering_label),
                            position=position,
                            active=True,
                            updated_at=now,
                        )
                    )
                    seen_ids.add(int(offering_id))
                else:
                    existing = connection.execute(
                        select(self.product_offerings)
                        .where(
                            self.product_offerings.c.product_id == product_id,
                            self.product_offerings.c.label == offering_label,
                        )
                        .order_by(self.product_offerings.c.id)
                        .limit(1)
                    ).mappings().first()
                    if existing:
                        existing_id = int(existing["id"])
                        connection.execute(
                            update(self.product_offerings)
                            .where(self.product_offerings.c.id == existing_id)
                            .values(
                                price=int(off["price"]),
                                net_weight_kg=_offering_net_weight(off, offering_label, existing),
                                position=position,
                                active=True,
                                updated_at=now,
                            )
                        )
                        seen_ids.add(existing_id)
                    else:
                        inserted_id = connection.execute(
                            insert(self.product_offerings)
                            .values(
                                product_id=product_id,
                                label=offering_label,
                                price=int(off["price"]),
                                net_weight_kg=_offering_net_weight(off, offering_label),
                                position=position,
                                active=True,
                                created_at=now,
                                updated_at=now,
                            )
                            .returning(self.product_offerings.c.id)
                        ).scalar_one()
                        seen_ids.add(inserted_id)

            for row in existing_rows:
                if row["id"] not in seen_ids:
                    connection.execute(
                        update(self.product_offerings)
                        .where(self.product_offerings.c.id == row["id"])
                        .values(active=False, updated_at=now)
                    )
            self._refresh_active_catalog_snapshot(connection=connection, now=now)

    def update_price_list_product(self, price_list_id: int, product: CatalogProductData, offerings: list[CatalogOfferingData]) -> CatalogProductData:
        now = utc_now()
        product_id = product.get("id") if isinstance(product.get("id"), int) else None
        product_name = str(product.get("name") or "").strip()
        if not product_name:
            raise ValueError("El producto debe tener nombre")

        normalized_offerings = [
            {
                "id": offering.get("id") if isinstance(offering.get("id"), int) else None,
                "label": str(offering.get("label") or "").strip(),
                "price": int(offering.get("price") or 0),
                "net_weight_kg": float(offering.get("net_weight_kg") or 0),
            }
            for offering in offerings
            if str(offering.get("label") or "").strip()
        ]

        with self.engine.begin() as connection:
            price_list = connection.execute(
                select(self.price_lists.c.id, self.price_lists.c.active).where(self.price_lists.c.id == price_list_id)
            ).mappings().first()
            if not price_list:
                raise ValueError("Lista de precios no encontrada")

            catalog_row = connection.execute(
                select(self.catalogs.c.id, self.catalogs.c.catalog)
                .where(self.catalogs.c.price_list_id == price_list_id)
                .order_by(self.catalogs.c.active.desc(), self.catalogs.c.id.desc())
                .limit(1)
                .with_for_update()
            ).mappings().first()
            if not catalog_row:
                raise ValueError("Catalogo de lista no encontrado")

            catalog = cast(list[CatalogProductData], serialize_value(catalog_row["catalog"] or []))
            numeric_product_ids = [int(item["id"]) for item in catalog if isinstance(item.get("id"), int)]
            numeric_offering_ids = [
                int(offering["id"])
                for item in catalog
                for offering in item.get("offerings", [])
                if isinstance(offering.get("id"), int)
            ]
            next_product_id = (min(numeric_product_ids) - 1) if numeric_product_ids else -1
            next_offering_id = (min(numeric_offering_ids) - 1) if numeric_offering_ids else -1

            target_index = next((index for index, item in enumerate(catalog) if product_id is not None and item.get("id") == product_id), None)
            if target_index is None:
                target_index = next((index for index, item in enumerate(catalog) if item.get("name") == product_name), None)

            if product_id is None:
                product_id = int(catalog[target_index]["id"]) if target_index is not None and isinstance(catalog[target_index].get("id"), int) else (next_product_id if not price_list["active"] else None)

            next_offerings: list[CatalogOfferingData] = []
            for offering in normalized_offerings:
                offering_id = offering.get("id")
                if not isinstance(offering_id, int):
                    offering_id = next_offering_id if not price_list["active"] else None
                    next_offering_id -= 1
                next_offerings.append(
                    {
                        "id": offering_id,
                        "label": offering["label"],
                        "price": int(offering["price"]),
                        "net_weight_kg": float(offering.get("net_weight_kg") or 0),
                    }
                )

            updated_product: CatalogProductData = {
                "id": product_id,
                "name": product_name,
                "aliases": product.get("aliases", []),
                "iva_rate": product.get("iva_rate"),
                "offerings": next_offerings,
            }
            if target_index is None:
                catalog.append(updated_product)
            else:
                catalog[target_index] = updated_product

            if price_list["active"]:
                self._sync_catalog_tables(catalog, connection=connection, now=now)
                catalog = self._catalog_snapshot(connection=connection)
                updated_product = next(
                    (item for item in catalog if item.get("name") == product_name),
                    updated_product,
                )

            connection.execute(
                update(self.catalogs)
                .where(self.catalogs.c.id == catalog_row["id"])
                .values(catalog=catalog, updated_at=now)
            )
            connection.execute(update(self.price_lists).where(self.price_lists.c.id == price_list_id).values(updated_at=now))

        return cast(CatalogProductData, serialize_value(updated_product))

    def delete_product(self, product_id: int) -> None:
        now = utc_now()
        with self.engine.begin() as connection:
            connection.execute(self.products.delete().where(self.products.c.id == product_id))
            self._refresh_active_catalog_snapshot(connection=connection, now=now)

    def replace_active_catalog(self, catalog: list[CatalogProductData], name: str = "Lista activa", price_list_id: int | None = None, active: bool = True) -> dict[str, object]:
        now = utc_now()
        with self.engine.begin() as connection:
            if active:
                connection.execute(update(self.catalogs).where(self.catalogs.c.active.is_(True)).values(active=False, updated_at=now))
                self._sync_catalog_tables(catalog, connection=connection, now=now)
                normalized_catalog = self._catalog_snapshot(connection=connection)
            else:
                normalized_catalog = catalog
            payload = {
                "price_list_id": price_list_id,
                "name": name,
                "active": active,
                "source": "manual_refresh",
                "catalog": normalized_catalog,
                "created_at": now,
                "updated_at": now,
            }
            connection.execute(self.catalogs.insert().values(**payload))
        return cast(dict[str, object], serialize_value(payload))

    def save_price_list_with_catalog(
        self,
        *,
        filename: str,
        pdf_bytes: bytes,
        catalog: list[CatalogProductData],
        activate: bool = True,
        source: str = "upload",
        name: str | None = None,
        price_list_id: int | None = None,
    ) -> PriceListMetaData:
        now = utc_now()
        with self.engine.begin() as connection:
            existing_name = None
            if price_list_id is not None:
                existing_name = connection.execute(
                    select(self.price_lists.c.name).where(self.price_lists.c.id == price_list_id)
                ).scalar_one_or_none()
                if existing_name is None:
                    raise RuntimeError("Lista de precios no encontrada")

            if activate:
                connection.execute(update(self.price_lists).where(self.price_lists.c.active.is_(True)).values(active=False, updated_at=now))
                connection.execute(update(self.catalogs).where(self.catalogs.c.active.is_(True)).values(active=False, updated_at=now))
            elif price_list_id is not None:
                connection.execute(update(self.catalogs).where(self.catalogs.c.price_list_id == price_list_id).values(active=False, updated_at=now))

            price_list_payload = {
                "name": name or existing_name or filename,
                "filename": filename,
                "content_type": "application/pdf",
                "size": len(pdf_bytes),
                "pdf_data": pdf_bytes,
                "active": activate,
                "source": source,
                "uploaded_at": now,
                "updated_at": now,
            }
            if price_list_id is not None:
                connection.execute(update(self.price_lists).where(self.price_lists.c.id == price_list_id).values(**price_list_payload))
                saved_price_list_id = price_list_id
            else:
                saved_price_list_id = int(connection.execute(self.price_lists.insert().values(**price_list_payload).returning(self.price_lists.c.id)).scalar_one())

            if activate:
                self._sync_catalog_tables(catalog, connection=connection, now=now)
                normalized_catalog = self._catalog_snapshot(connection=connection)
            else:
                normalized_catalog = catalog

            catalog_payload = {
                "price_list_id": saved_price_list_id,
                "name": f"Catalogo desde {price_list_payload['name']}",
                "active": activate,
                "source": source,
                "catalog": normalized_catalog,
                "created_at": now,
                "updated_at": now,
            }
            connection.execute(self.catalogs.insert().values(**catalog_payload))

        price_list_payload["id"] = saved_price_list_id
        price_list_payload.pop("pdf_data", None)
        return cast(PriceListMetaData, serialize_value(price_list_payload))

    def list_price_lists(self) -> list[PriceListMetaData]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(self.price_lists.c.id, self.price_lists.c.name, self.price_lists.c.filename, self.price_lists.c.content_type, self.price_lists.c.size, self.price_lists.c.active, self.price_lists.c.source, self.price_lists.c.uploaded_at, self.price_lists.c.updated_at)
                .order_by(self.price_lists.c.active.desc(), self.price_lists.c.id.desc())
            ).mappings().all()
        return cast(list[PriceListMetaData], [{key: serialize_value(value) for key, value in row.items()} for row in rows])

    def get_catalog_for_price_list(self, price_list_id: int) -> list[CatalogProductData]:
        with self.engine.connect() as connection:
            catalog = connection.execute(
                select(self.catalogs.c.catalog)
                .where(self.catalogs.c.price_list_id == price_list_id)
                .order_by(self.catalogs.c.active.desc(), self.catalogs.c.id.desc())
                .limit(1)
            ).scalar_one_or_none()
        if not catalog:
            raise RuntimeError("Lista de precios no encontrada")
        return cast(list[CatalogProductData], serialize_value(catalog))

    def delete_price_list(self, price_list_id: int) -> None:
        now = utc_now()
        with self.engine.begin() as connection:
            row = connection.execute(
                select(self.price_lists.c.id, self.price_lists.c.active).where(self.price_lists.c.id == price_list_id)
            ).mappings().first()
            if not row:
                raise ValueError("Lista de precios no encontrada")

            connection.execute(
                update(self.invoices)
                .where(self.invoices.c.price_list_id == price_list_id)
                .values(price_list_id=None)
            )
            connection.execute(self.catalogs.delete().where(self.catalogs.c.price_list_id == price_list_id))
            connection.execute(self.price_lists.delete().where(self.price_lists.c.id == price_list_id))

            if row["active"]:
                replacement = connection.execute(
                    select(self.price_lists.c.id)
                    .order_by(self.price_lists.c.id.desc())
                    .limit(1)
                ).scalar_one_or_none()
                if replacement is not None:
                    connection.execute(
                        update(self.price_lists)
                        .where(self.price_lists.c.id == replacement)
                        .values(active=True, updated_at=now)
                    )
                    connection.execute(
                        update(self.catalogs)
                        .where(self.catalogs.c.price_list_id == replacement)
                        .values(active=True, updated_at=now)
                    )

    def rename_price_list(self, price_list_id: int, name: str) -> None:
        now = utc_now()
        with self.engine.begin() as connection:
            result = connection.execute(
                update(self.price_lists)
                .where(self.price_lists.c.id == price_list_id)
                .values(name=name, updated_at=now)
            )
            if result.rowcount == 0:
                raise ValueError("Lista de precios no encontrada")

    def get_active_price_list_meta(self) -> PriceListMetaData | None:
        with self.engine.connect() as connection:
            row = connection.execute(
                select(self.price_lists.c.id, self.price_lists.c.name, self.price_lists.c.filename, self.price_lists.c.content_type, self.price_lists.c.size, self.price_lists.c.active, self.price_lists.c.source, self.price_lists.c.uploaded_at, self.price_lists.c.updated_at)
                .where(self.price_lists.c.active.is_(True))
                .order_by(self.price_lists.c.id.desc())
                .limit(1)
            ).mappings().first()
        if not row:
            return None
        payload: PriceListMetaData = cast(PriceListMetaData, {key: serialize_value(value) for key, value in row.items()})
        return payload

    def save_price_list(self, filename: str, pdf_bytes: bytes, activate: bool = True, source: str = "upload", name: str | None = None, price_list_id: int | None = None) -> PriceListMetaData:
        now = utc_now()
        existing_name = None
        if price_list_id is not None:
            with self.engine.connect() as connection:
                existing_name = connection.execute(
                    select(self.price_lists.c.name).where(self.price_lists.c.id == price_list_id)
                ).scalar_one_or_none()
            if existing_name is None:
                raise RuntimeError("Lista de precios no encontrada")
        payload = {
            "name": name or existing_name or filename,
            "filename": filename,
            "content_type": "application/pdf",
            "size": len(pdf_bytes),
            "pdf_data": pdf_bytes,
            "active": activate,
            "source": source,
            "uploaded_at": now,
            "updated_at": now,
        }
        with self.engine.begin() as connection:
            if activate:
                connection.execute(update(self.price_lists).where(self.price_lists.c.active.is_(True)).values(active=False, updated_at=now))
            if price_list_id is not None:
                connection.execute(update(self.price_lists).where(self.price_lists.c.id == price_list_id).values(**payload))
                payload["id"] = price_list_id
            else:
                inserted = connection.execute(self.price_lists.insert().values(**payload).returning(self.price_lists.c.id)).scalar_one()
                payload["id"] = inserted
        payload.pop("pdf_data", None)
        return cast(PriceListMetaData, serialize_value(payload))

    def _sync_customer_references(self, *, connection, now) -> None:
        customer_rows = connection.execute(select(self.customers)).mappings().all()
        for row in customer_rows:
            _mode, footer_discounts, line_discounts_by_format = canonicalize_discount_config(
                row.get("footer_discounts"),
                row.get("line_discounts_by_format"),
            )
            connection.execute(
                update(self.customers)
                .where(self.customers.c.id == row["id"])
                .values(
                    footer_discounts=footer_discounts,
                    line_discounts_by_format=line_discounts_by_format,
                    updated_at=now,
                )
            )

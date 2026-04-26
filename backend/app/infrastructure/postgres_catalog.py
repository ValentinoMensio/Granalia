from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.engine import Engine
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.sql.schema import Table
from typing import cast

from ..core.utils import canonicalize_discount_config
from ..types import CatalogOfferingData, CatalogProductData, PriceListMetaData
from .postgres_protocol import PostgresRepositoryProtocol
from .postgres_utils import serialize_value, utc_now


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
                }
            )

        return [
            {
                "id": row["id"],
                "name": row["name"],
                "aliases": row["aliases"],
                "offerings": offerings_by_product.get(row["id"], []),
            }
            for row in product_rows
        ]

    def _sync_catalog_tables(self, catalog: list[CatalogProductData], *, connection, now) -> None:
        active_product_db_ids: set[int] = set()
        active_offering_db_ids: set[int] = set()

        connection.execute(update(self.products).values(active=False, updated_at=now))
        connection.execute(update(self.product_offerings).values(active=False, updated_at=now))

        for product in catalog:
            product_name = product["name"]
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
                    connection.execute(
                        update(self.product_offerings)
                        .where(self.product_offerings.c.id == offering_id)
                        .values(
                            product_id=product_db_id,
                            label=offering_label,
                            price=int(offering["price"]),
                            position=position,
                            active=True,
                            updated_at=now,
                        )
                    )
                    active_offering_db_ids.add(int(offering_id))
                else:
                    offering_stmt = insert(self.product_offerings).values(
                        product_id=product_db_id,
                        label=offering_label,
                        price=int(offering["price"]),
                        position=position,
                        active=True,
                        created_at=now,
                        updated_at=now,
                    )
                    offering_stmt = offering_stmt.on_conflict_do_update(
                        index_elements=[self.product_offerings.c.product_id, self.product_offerings.c.label],
                        set_={
                            "price": int(offering["price"]),
                            "position": position,
                            "active": True,
                            "updated_at": now,
                        },
                    ).returning(self.product_offerings.c.id)
                    active_offering_db_ids.add(int(connection.execute(offering_stmt).scalar_one()))

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
                            active=True,
                            created_at=now,
                            updated_at=now,
                        )
                        .returning(self.products)
                    ).mappings().first()
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

    def delete_product(self, product_id: int) -> None:
        with self.engine.begin() as connection:
            connection.execute(self.products.delete().where(self.products.c.id == product_id))

    def replace_active_catalog(self, catalog: list[CatalogProductData], name: str = "Lista activa") -> dict[str, object]:
        now = utc_now()
        with self.engine.begin() as connection:
            connection.execute(update(self.catalogs).where(self.catalogs.c.active.is_(True)).values(active=False, updated_at=now))
            self._sync_catalog_tables(catalog, connection=connection, now=now)
            normalized_catalog = self._catalog_snapshot(connection=connection)
            payload = {
                "name": name,
                "active": True,
                "source": "manual_refresh",
                "catalog": normalized_catalog,
                "created_at": now,
                "updated_at": now,
            }
            connection.execute(self.catalogs.insert().values(**payload))
        return cast(dict[str, object], serialize_value(payload))

    def get_active_price_list_meta(self) -> PriceListMetaData | None:
        with self.engine.connect() as connection:
            row = connection.execute(
                select(self.price_lists.c.id, self.price_lists.c.filename, self.price_lists.c.content_type, self.price_lists.c.size, self.price_lists.c.active, self.price_lists.c.source, self.price_lists.c.uploaded_at, self.price_lists.c.updated_at)
                .where(self.price_lists.c.active.is_(True))
                .order_by(self.price_lists.c.id.desc())
                .limit(1)
            ).mappings().first()
        if not row:
            return None
        payload: PriceListMetaData = cast(PriceListMetaData, {key: serialize_value(value) for key, value in row.items()})
        return payload

    def save_price_list(self, filename: str, pdf_bytes: bytes, activate: bool = True, source: str = "upload") -> PriceListMetaData:
        now = utc_now()
        payload = {
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
            connection.execute(self.price_lists.insert().values(**payload))
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

from __future__ import annotations

from sqlalchemy import select, text, update
from sqlalchemy.engine import Engine
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.sql.schema import Table

from .postgres_protocol import PostgresRepositoryProtocol
from .postgres_utils import utc_now


class PostgresMigrationMixin(PostgresRepositoryProtocol):
    engine: Engine
    catalogs: Table
    transports: Table
    customers: Table
    products: Table
    product_offerings: Table
    invoice_batches: Table
    invoices: Table
    invoice_items: Table
    invoice_tax_breakdown: Table
    arca_requests: Table

    def _column_exists(self, connection, table_name: str, column_name: str) -> bool:
        return bool(
            connection.execute(
                text(
                    """
                    select 1
                    from information_schema.columns
                    where table_schema = 'public'
                      and table_name = :table_name
                      and column_name = :column_name
                    """
                ),
                {"table_name": table_name, "column_name": column_name},
            ).scalar()
        )

    def _table_exists(self, connection, table_name: str) -> bool:
        return bool(
            connection.execute(
                text(
                    """
                    select 1
                    from information_schema.tables
                    where table_schema = 'public'
                      and table_name = :table_name
                    """
                ),
                {"table_name": table_name},
            ).scalar()
        )

    def _is_numeric_column(self, connection, table_name: str, column_name: str) -> bool:
        return bool(
            connection.execute(
                text(
                    """
                    select 1
                    from information_schema.columns
                    where table_schema = 'public'
                      and table_name = :table_name
                      and column_name = :column_name
                      and data_type = 'numeric'
                    """
                ),
                {"table_name": table_name, "column_name": column_name},
            ).scalar()
        )

    def _ensure_customer_billing_fields(self, *, connection) -> None:
        if not self._table_exists(connection, "customers"):
            return

        fields = [
            ("cuit", "VARCHAR(32) NOT NULL DEFAULT ''"),
            ("address", "TEXT NOT NULL DEFAULT ''"),
            ("business_name", "VARCHAR(255) NOT NULL DEFAULT ''"),
            ("email", "VARCHAR(255) NOT NULL DEFAULT ''"),
        ]
        for column_name, definition in fields:
            if self._column_exists(connection, "customers", column_name):
                continue
            connection.execute(text(f"ALTER TABLE customers ADD COLUMN {column_name} {definition}"))

    def _migrate_catalog_snapshots(self, *, connection) -> None:
        rows = connection.execute(
            select(self.catalogs.c.id, self.catalogs.c.catalog).order_by(self.catalogs.c.id)
        ).mappings().all()
        if not rows:
            return

        products = connection.execute(select(self.products)).mappings().all()
        product_by_name = {row["name"]: row for row in products}
        product_by_id = {row["id"]: row for row in products}
        offerings = connection.execute(select(self.product_offerings)).mappings().all()
        offering_by_label = {
            (product_by_id[row["product_id"]]["name"], row["label"]): row
            for row in offerings
            if row["product_id"] in product_by_id
        }

        for row in rows:
            normalized_catalog = []
            for product in row["catalog"] or []:
                product_name = product.get("name", "")
                product_row = product_by_name.get(product_name)
                normalized_product = {
                    "id": product_row["id"] if product_row else product.get("id"),
                    "name": product_name,
                    "aliases": product.get("aliases", []),
                    "iva_rate": float(product_row["iva_rate"]) if product_row and product_row.get("iva_rate") is not None else product.get("iva_rate"),
                    "offerings": [],
                }
                for offering in product.get("offerings", []):
                    offering_label = offering.get("label", "")
                    offering_row = offering_by_label.get((product_name, offering_label))
                    normalized_product["offerings"].append(
                        {
                            "id": offering_row["id"] if offering_row else offering.get("id"),
                            "label": offering_label,
                            "price": int(offering.get("price", 0)),
                            "net_weight_kg": float(offering.get("net_weight_kg") or 0),
                        }
                    )
                normalized_catalog.append(normalized_product)

            connection.execute(
                update(self.catalogs)
                .where(self.catalogs.c.id == row["id"])
                .values(catalog=normalized_catalog)
            )

    def _migrate_legacy_schema(self) -> None:
        with self.engine.begin() as connection:
            if self._table_exists(connection, "customers") and self._column_exists(connection, "customers", "id"):
                return

            if not self._table_exists(connection, "customers"):
                return

            connection.execute(text("DROP TABLE IF EXISTS invoice_items_new"))
            connection.execute(text("DROP TABLE IF EXISTS invoices_new"))
            connection.execute(text("DROP TABLE IF EXISTS product_offerings_new"))
            connection.execute(text("DROP TABLE IF EXISTS products_new"))
            connection.execute(text("DROP TABLE IF EXISTS customers_new"))

            connection.execute(text("""
                CREATE TABLE customers_new (
                    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    customer_key VARCHAR(255) NOT NULL UNIQUE,
                    name VARCHAR(255) NOT NULL,
                    secondary_line TEXT NOT NULL DEFAULT '',
                    notes JSONB NOT NULL,
                    footer_discounts JSONB NOT NULL,
                    line_discounts_by_format JSONB NOT NULL,
                    source_count INTEGER NOT NULL DEFAULT 0,
                    transport_id BIGINT REFERENCES transports(transport_id) ON DELETE SET NULL,
                    created_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL
                )
            """))
            connection.execute(text("""
                INSERT INTO customers_new (
                    customer_key, name, secondary_line, notes,
                    footer_discounts, line_discounts_by_format,
                    source_count, transport_id, created_at, updated_at
                )
                SELECT
                    customer_key, name, secondary_line, notes,
                    footer_discounts, line_discounts_by_format,
                    source_count, transport_id, created_at, updated_at
                FROM customers
                ORDER BY created_at, customer_key
            """))

            connection.execute(text("""
                CREATE TABLE products_new (
                    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    aliases JSONB NOT NULL,
                    active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL
                )
            """))
            connection.execute(text("""
                INSERT INTO products_new (name, aliases, active, created_at, updated_at)
                SELECT name, aliases, active, created_at, updated_at
                FROM products
                ORDER BY created_at, product_id
            """))

            connection.execute(text("""
                CREATE TABLE product_offerings_new (
                    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    product_id BIGINT NOT NULL REFERENCES products_new(id) ON DELETE CASCADE,
                    label VARCHAR(120) NOT NULL,
                    price INTEGER NOT NULL,
                    position INTEGER NOT NULL,
                    active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL,
                    UNIQUE(product_id, label)
                )
            """))
            connection.execute(text("""
                INSERT INTO product_offerings_new (
                    product_id, label, price, position, active, created_at, updated_at
                )
                SELECT
                    products_new.id,
                    product_offerings.label,
                    product_offerings.price,
                    product_offerings.position,
                    product_offerings.active,
                    product_offerings.created_at,
                    product_offerings.updated_at
                FROM product_offerings
                JOIN products_new ON products_new.name = product_offerings.product_id
                ORDER BY product_offerings.created_at, product_offerings.offering_key
            """))

            connection.execute(text("""
                CREATE TABLE invoices_new (
                    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    customer_id BIGINT REFERENCES customers_new(id) ON DELETE SET NULL,
                    transport_id BIGINT REFERENCES transports(transport_id) ON DELETE SET NULL,
                    legacy_key VARCHAR(255) UNIQUE,
                    client_name VARCHAR(255) NOT NULL,
                    order_date DATE NOT NULL,
                    secondary_line TEXT NOT NULL DEFAULT '',
                    transport TEXT NOT NULL DEFAULT '',
                    notes JSONB NOT NULL,
                    footer_discounts JSONB NOT NULL,
                    line_discounts_by_format JSONB NOT NULL,
                    total_bultos INTEGER NOT NULL,
                    gross_total INTEGER NOT NULL,
                    discount_total INTEGER NOT NULL,
                    final_total INTEGER NOT NULL,
                    output_filename VARCHAR(255) NOT NULL,
                    xlsx_data BYTEA NOT NULL,
                    xlsx_size INTEGER NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL
                )
            """))
            connection.execute(text("""
                INSERT INTO invoices_new (
                    customer_id, transport_id, legacy_key, client_name,
                    order_date, secondary_line, transport, notes,
                    footer_discounts, line_discounts_by_format, total_bultos,
                    gross_total, discount_total, final_total, output_filename,
                    xlsx_data, xlsx_size, created_at
                )
                SELECT
                    customers_new.id,
                    invoices.transport_id,
                    invoices.invoice_id,
                    invoices.client_name,
                    invoices.order_date,
                    invoices.secondary_line,
                    invoices.transport,
                    invoices.notes,
                    invoices.footer_discounts,
                    invoices.line_discounts_by_format,
                    invoices.total_bultos,
                    invoices.gross_total,
                    invoices.discount_total,
                    invoices.final_total,
                    invoices.output_filename,
                    invoices.xlsx_data,
                    invoices.xlsx_size,
                    invoices.created_at
                FROM invoices
                LEFT JOIN customers_new ON customers_new.customer_key = invoices.customer_key
                ORDER BY invoices.created_at, invoices.invoice_id
            """))

            connection.execute(text("""
                CREATE TABLE invoice_items_new (
                    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    invoice_id BIGINT NOT NULL REFERENCES invoices_new(id) ON DELETE CASCADE,
                    line_number INTEGER NOT NULL,
                    product_id BIGINT REFERENCES products_new(id) ON DELETE SET NULL,
                    offering_id BIGINT REFERENCES product_offerings_new(id) ON DELETE SET NULL,
                    label TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    unit_price INTEGER NOT NULL,
                    gross INTEGER NOT NULL,
                    discount INTEGER NOT NULL,
                    total INTEGER NOT NULL
                )
            """))
            connection.execute(text("""
                INSERT INTO invoice_items_new (
                    id, invoice_id, line_number, product_id, offering_id,
                    label, quantity, unit_price, gross, discount, total
                )
                SELECT
                    invoice_items.id,
                    invoices_new.id,
                    invoice_items.line_number,
                    products_new.id,
                    product_offerings_new.id,
                    invoice_items.label,
                    invoice_items.quantity,
                    invoice_items.unit_price,
                    invoice_items.gross,
                    invoice_items.discount,
                    invoice_items.total
                FROM invoice_items
                JOIN invoices_new ON invoices_new.legacy_key = invoice_items.invoice_id
                LEFT JOIN products_new ON products_new.name = invoice_items.product_id
                LEFT JOIN product_offerings_new
                    ON product_offerings_new.product_id = products_new.id
                   AND product_offerings_new.label = invoice_items.label
                ORDER BY invoice_items.id
            """))
            connection.execute(text("SELECT setval(pg_get_serial_sequence('invoice_items_new', 'id'), COALESCE((SELECT MAX(id) FROM invoice_items_new), 1), true)"))

            connection.execute(text("DROP TABLE invoice_items"))
            connection.execute(text("DROP TABLE invoices"))
            connection.execute(text("DROP TABLE product_offerings"))
            connection.execute(text("DROP TABLE products"))
            connection.execute(text("DROP TABLE customers"))

            connection.execute(text("ALTER TABLE customers_new RENAME TO customers"))
            connection.execute(text("ALTER TABLE products_new RENAME TO products"))
            connection.execute(text("ALTER TABLE product_offerings_new RENAME TO product_offerings"))
            connection.execute(text("ALTER TABLE invoices_new RENAME TO invoices"))
            connection.execute(text("ALTER TABLE invoice_items_new RENAME TO invoice_items"))

            if self._table_exists(connection, "client_profiles"):
                connection.execute(text("DROP TABLE client_profiles"))

    def _drop_customer_key_column(self, *, connection) -> None:
        if not self._table_exists(connection, "customers") or not self._column_exists(connection, "customers", "customer_key"):
            return

        connection.execute(text("ALTER TABLE customers DROP COLUMN customer_key"))

    def _drop_discount_policy_schema(self, *, connection) -> None:
        if self._table_exists(connection, "invoices"):
            connection.execute(text("ALTER TABLE invoices DROP COLUMN IF EXISTS discount_policy_id"))

        if self._table_exists(connection, "customers"):
            connection.execute(text("ALTER TABLE customers DROP COLUMN IF EXISTS discount_policy_id"))

        if self._table_exists(connection, "discount_policies"):
            connection.execute(text("DROP TABLE discount_policies"))

    def _drop_mode_columns(self, *, connection) -> None:
        if self._table_exists(connection, "invoices"):
            connection.execute(text("ALTER TABLE invoices DROP COLUMN IF EXISTS mode"))

        if self._table_exists(connection, "customers"):
            connection.execute(text("ALTER TABLE customers DROP COLUMN IF EXISTS mode"))

    def _drop_line_discount_label_columns(self, *, connection) -> None:
        if self._table_exists(connection, "customers"):
            connection.execute(text("ALTER TABLE customers DROP COLUMN IF EXISTS line_discount_label"))

    def _drop_product_code_column(self, *, connection) -> None:
        if self._table_exists(connection, "products"):
            connection.execute(text("ALTER TABLE products DROP COLUMN IF EXISTS code"))

    def _drop_offering_code_column(self, *, connection) -> None:
        if self._table_exists(connection, "product_offerings"):
            connection.execute(text("ALTER TABLE product_offerings DROP COLUMN IF EXISTS code"))

    def _drop_offering_format_class_column(self, *, connection) -> None:
        if self._table_exists(connection, "product_offerings"):
            connection.execute(text("ALTER TABLE product_offerings DROP COLUMN IF EXISTS format_class"))

    def _resolve_transport_id(self, *, connection, transport_name: str | None, now) -> int | None:
        name = str(transport_name or "").strip()
        if not name:
            return None

        stmt = insert(self.transports).values(
            name=name,
            notes=[],
            created_at=now,
            updated_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[self.transports.c.name],
            set_={"updated_at": now},
        )
        connection.execute(stmt)
        return int(
            connection.execute(
                select(self.transports.c.transport_id).where(self.transports.c.name == name)
            ).scalar_one()
        )

    def _migrate_customer_transport_reference(self, *, connection) -> None:
        if not self._table_exists(connection, "customers") or not self._column_exists(connection, "customers", "transport"):
            return

        rows = connection.execute(
            text("SELECT id, transport, transport_id FROM customers ORDER BY id")
        ).mappings().all()
        now = utc_now()
        for row in rows:
            if row.get("transport_id"):
                continue
            transport_id = self._resolve_transport_id(connection=connection, transport_name=row.get("transport"), now=now)
            if transport_id is None:
                continue
            connection.execute(
                update(self.customers)
                .where(self.customers.c.id == row["id"])
                .values(transport_id=transport_id, updated_at=now)
            )

    def _migrate_invoice_transport_snapshot(self, *, connection) -> None:
        if not self._table_exists(connection, "invoices"):
            return
        if not self._column_exists(connection, "invoices", "transport") or not self._column_exists(connection, "invoices", "transport_id"):
            return

        connection.execute(
            text(
                """
                UPDATE invoices i
                SET transport = t.name
                FROM transports t
                WHERE i.transport_id = t.transport_id
                  AND COALESCE(TRIM(i.transport), '') = ''
                """
            )
        )

    def _ensure_invoice_transport_reference(self, *, connection) -> None:
        if not self._table_exists(connection, "invoices"):
            return

        if not self._column_exists(connection, "invoices", "transport_id"):
            connection.execute(
                text(
                    """
                    ALTER TABLE invoices
                    ADD COLUMN transport_id BIGINT REFERENCES transports(transport_id) ON DELETE SET NULL
                    """
                )
            )

        if not self._column_exists(connection, "invoices", "transport"):
            return

        rows = connection.execute(
            text("SELECT id, transport, transport_id FROM invoices ORDER BY id")
        ).mappings().all()
        now = utc_now()
        for row in rows:
            if row.get("transport_id"):
                continue
            transport_id = self._resolve_transport_id(connection=connection, transport_name=row.get("transport"), now=now)
            if transport_id is None:
                continue
            connection.execute(
                update(self.invoices)
                .where(self.invoices.c.id == row["id"])
                .values(transport_id=transport_id)
            )

    def _ensure_fractional_invoice_quantities(self, *, connection) -> None:
        if self._table_exists(connection, "invoice_items") and not self._is_numeric_column(connection, "invoice_items", "quantity"):
            connection.execute(text("ALTER TABLE invoice_items ALTER COLUMN quantity TYPE NUMERIC(12, 2) USING quantity::numeric"))
        if self._table_exists(connection, "invoices") and not self._is_numeric_column(connection, "invoices", "total_bultos"):
            connection.execute(text("ALTER TABLE invoices ALTER COLUMN total_bultos TYPE NUMERIC(12, 2) USING total_bultos::numeric"))

    def _ensure_price_list_invoice_fields(self, *, connection) -> None:
        if self._table_exists(connection, "price_lists") and not self._column_exists(connection, "price_lists", "name"):
            connection.execute(text("ALTER TABLE price_lists ADD COLUMN name VARCHAR(255) NOT NULL DEFAULT 'Lista principal'"))
        if self._table_exists(connection, "catalogs") and not self._column_exists(connection, "catalogs", "price_list_id"):
            connection.execute(text("ALTER TABLE catalogs ADD COLUMN price_list_id BIGINT REFERENCES price_lists(id) ON DELETE SET NULL"))
            connection.execute(text("UPDATE catalogs c SET price_list_id = p.id FROM price_lists p WHERE c.active = true AND p.active = true"))
        if self._table_exists(connection, "invoices"):
            if not self._column_exists(connection, "invoices", "price_list_id"):
                connection.execute(text("ALTER TABLE invoices ADD COLUMN price_list_id BIGINT REFERENCES price_lists(id) ON DELETE SET NULL"))
            if not self._column_exists(connection, "invoices", "declared"):
                connection.execute(text("ALTER TABLE invoices ADD COLUMN declared BOOLEAN NOT NULL DEFAULT false"))
            if not self._column_exists(connection, "invoices", "price_list_name"):
                connection.execute(text("ALTER TABLE invoices ADD COLUMN price_list_name VARCHAR(255) NOT NULL DEFAULT ''"))
            connection.execute(text("UPDATE invoices i SET price_list_id = p.id, price_list_name = p.name FROM price_lists p WHERE p.active = true AND COALESCE(i.price_list_name, '') = ''"))

    def _ensure_invoice_historical_snapshot_fields(self, *, connection) -> None:
        if self._table_exists(connection, "invoices"):
            invoice_fields = [
                ("price_list_effective_date", "TIMESTAMP WITH TIME ZONE"),
                ("customer_cuit", "VARCHAR(32)"),
                ("customer_address", "TEXT"),
                ("customer_business_name", "VARCHAR(255)"),
                ("customer_email", "VARCHAR(255)"),
            ]
            for column_name, definition in invoice_fields:
                if not self._column_exists(connection, "invoices", column_name):
                    connection.execute(text(f"ALTER TABLE invoices ADD COLUMN {column_name} {definition}"))
            connection.execute(
                text(
                    """
                    UPDATE invoices i
                    SET
                        customer_cuit = COALESCE(NULLIF(i.customer_cuit, ''), c.cuit, ''),
                        customer_address = COALESCE(NULLIF(i.customer_address, ''), c.address, ''),
                        customer_business_name = COALESCE(NULLIF(i.customer_business_name, ''), c.business_name, ''),
                        customer_email = COALESCE(NULLIF(i.customer_email, ''), c.email, '')
                    FROM customers c
                    WHERE i.customer_id = c.id
                    """
                )
            )
            connection.execute(
                text(
                    """
                    UPDATE invoices i
                    SET price_list_effective_date = COALESCE(i.price_list_effective_date, p.uploaded_at)
                    FROM price_lists p
                    WHERE i.price_list_id = p.id
                    """
                )
            )

        if self._table_exists(connection, "invoice_items"):
            item_fields = [
                ("product_name", "VARCHAR(255)"),
                ("offering_label", "VARCHAR(120)"),
                ("offering_net_weight_kg", "NUMERIC(12, 3)"),
                ("line_type", "VARCHAR(20)"),
                ("discount_rate", "NUMERIC(8, 6)"),
            ]
            for column_name, definition in item_fields:
                if not self._column_exists(connection, "invoice_items", column_name):
                    connection.execute(text(f"ALTER TABLE invoice_items ADD COLUMN {column_name} {definition}"))

            connection.execute(
                text(
                    """
                    UPDATE invoice_items ii
                    SET
                        product_name = COALESCE(NULLIF(ii.product_name, ''), p.name, ''),
                        offering_label = COALESCE(NULLIF(ii.offering_label, ''), po.label, ''),
                        offering_net_weight_kg = CASE
                            WHEN ii.offering_net_weight_kg > 0 THEN ii.offering_net_weight_kg
                            ELSE COALESCE(po.net_weight_kg, 0)
                        END,
                        line_type = CASE WHEN ii.unit_price = 0 THEN 'bonus' ELSE COALESCE(NULLIF(ii.line_type, ''), 'sale') END,
                        discount_rate = CASE
                            WHEN ii.gross > 0 AND ii.discount > 0 THEN ROUND((ii.discount::numeric / ii.gross::numeric), 6)
                            ELSE COALESCE(ii.discount_rate, 0)
                        END
                    FROM products p, product_offerings po
                    WHERE ii.product_id = p.id
                      AND ii.offering_id = po.id
                    """
                )
            )
            connection.execute(text("UPDATE invoice_items SET line_type = CASE WHEN unit_price = 0 THEN 'bonus' ELSE 'sale' END WHERE line_type IS NULL OR line_type NOT IN ('sale', 'bonus')"))
            connection.execute(text("ALTER TABLE invoice_items ALTER COLUMN line_type SET DEFAULT 'sale'"))
            connection.execute(text("ALTER TABLE invoice_items ALTER COLUMN line_type SET NOT NULL"))

    def _ensure_offering_net_weight(self, *, connection) -> None:
        if not self._table_exists(connection, "product_offerings"):
            return

        if not self._column_exists(connection, "product_offerings", "net_weight_kg"):
            connection.execute(text("ALTER TABLE product_offerings ADD COLUMN net_weight_kg NUMERIC(12, 3) NOT NULL DEFAULT 0"))

        connection.execute(
            text(
                """
                UPDATE product_offerings
                SET net_weight_kg = CASE
                    WHEN lower(replace(label, ' ', '')) LIKE '12x400%' THEN 4.8
                    WHEN lower(replace(label, ' ', '')) LIKE '16x300%' THEN 4.8
                    WHEN lower(replace(label, ' ', '')) LIKE '12x350%' THEN 4.2
                    WHEN lower(replace(label, ' ', '')) LIKE '10x500%' THEN 5
                    WHEN lower(replace(label, ' ', '')) LIKE '12x500%' THEN 6
                    WHEN lower(replace(label, ' ', '')) LIKE '10x1kg%' THEN 10
                    WHEN lower(replace(label, ' ', '')) LIKE '10x1000%' THEN 10
                    WHEN lower(replace(label, ' ', '')) LIKE 'x1kg%' THEN 1
                    WHEN lower(replace(label, ' ', '')) LIKE 'x4kg%' THEN 4
                    WHEN lower(replace(label, ' ', '')) LIKE 'x5kg%' THEN 5
                    WHEN lower(replace(label, ' ', '')) LIKE 'x25kg%' THEN 25
                    WHEN lower(replace(label, ' ', '')) LIKE 'x30kg%' THEN 30
                    ELSE net_weight_kg
                END
                WHERE COALESCE(net_weight_kg, 0) = 0
                """
            )
        )

    def _ensure_arca_fiscal_base(self, *, connection) -> None:
        if self._table_exists(connection, "products") and not self._column_exists(connection, "products", "iva_rate"):
            connection.execute(text("ALTER TABLE products ADD COLUMN iva_rate NUMERIC(5, 3)"))

        if not self._table_exists(connection, "invoice_batches"):
            connection.execute(
                text(
                    """
                    CREATE TABLE invoice_batches (
                        id BIGSERIAL PRIMARY KEY,
                        customer_id BIGINT REFERENCES customers(id) ON DELETE SET NULL,
                        client_name VARCHAR(255) NOT NULL,
                        order_date DATE NOT NULL,
                        billing_mode VARCHAR(30) NOT NULL,
                        declared_percentage NUMERIC(5, 2),
                        internal_percentage NUMERIC(5, 2),
                        internal_price_list_id BIGINT REFERENCES price_lists(id) ON DELETE SET NULL,
                        fiscal_price_list_id BIGINT REFERENCES price_lists(id) ON DELETE SET NULL,
                        created_by_user_id BIGINT,
                        created_at TIMESTAMPTZ NOT NULL
                    )
                    """
                )
            )

        if self._table_exists(connection, "invoices"):
            invoice_fields = [
                ("batch_id", "BIGINT REFERENCES invoice_batches(id) ON DELETE SET NULL"),
                ("split_kind", "VARCHAR(20)"),
                ("split_percentage", "NUMERIC(5, 2)"),
                ("fiscal_status", "VARCHAR(20) NOT NULL DEFAULT 'internal'"),
                ("fiscal_locked_at", "TIMESTAMPTZ"),
                ("fiscal_authorized_at", "TIMESTAMPTZ"),
                ("internal_invoice_number", "BIGINT"),
                ("arca_environment", "VARCHAR(20)"),
                ("arca_cuit_emisor", "VARCHAR(32)"),
                ("arca_cbte_tipo", "INTEGER"),
                ("arca_concepto", "INTEGER"),
                ("arca_doc_tipo", "INTEGER"),
                ("arca_doc_nro", "VARCHAR(32)"),
                ("arca_point_of_sale", "INTEGER"),
                ("arca_invoice_number", "BIGINT"),
                ("arca_cae", "VARCHAR(32)"),
                ("arca_cae_expires_at", "DATE"),
                ("arca_result", "VARCHAR(20)"),
                ("arca_observations", "JSONB"),
                ("arca_error_code", "VARCHAR(50)"),
                ("arca_error_message", "TEXT"),
                ("arca_request_id", "VARCHAR(120)"),
            ]
            for column_name, definition in invoice_fields:
                if not self._column_exists(connection, "invoices", column_name):
                    connection.execute(text(f"ALTER TABLE invoices ADD COLUMN {column_name} {definition}"))
            connection.execute(
                text(
                    """
                    UPDATE invoices
                    SET document_type = regexp_replace(document_type, '_DRAFT$', '')
                    WHERE right(document_type, 6) = '_DRAFT'
                    """
                )
            )
            connection.execute(
                text(
                    """
                    UPDATE invoices
                    SET internal_invoice_number = invoice_number
                    WHERE fiscal_status = 'internal'
                      AND internal_invoice_number IS NULL
                    """
                )
            )
            connection.execute(
                text(
                    """
                    UPDATE invoices
                    SET fiscal_status = 'authorized'
                    WHERE arca_cae IS NOT NULL
                      AND arca_invoice_number IS NOT NULL
                      AND fiscal_status <> 'authorized'
                    """
                )
            )
            connection.execute(text("ALTER TABLE invoices DROP CONSTRAINT IF EXISTS uq_invoices_fiscal_number"))
            connection.execute(text("ALTER TABLE invoices ALTER COLUMN invoice_number DROP NOT NULL"))
            connection.execute(text("ALTER TABLE invoices DROP CONSTRAINT IF EXISTS ck_invoices_invoice_number_positive"))
            connection.execute(text("ALTER TABLE invoices ADD CONSTRAINT ck_invoices_invoice_number_positive CHECK (invoice_number IS NULL OR invoice_number > 0)"))
            connection.execute(text("ALTER TABLE invoices DROP CONSTRAINT IF EXISTS ck_invoices_fiscal_status_valid"))
            connection.execute(text("ALTER TABLE invoices ADD CONSTRAINT ck_invoices_fiscal_status_valid CHECK (fiscal_status IN ('internal', 'draft', 'authorizing', 'authorized', 'rejected', 'error'))"))
            connection.execute(
                text(
                    """
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_constraint WHERE conname = 'ck_invoices_internal_invoice_number_positive'
                        ) THEN
                            ALTER TABLE invoices ADD CONSTRAINT ck_invoices_internal_invoice_number_positive CHECK (internal_invoice_number IS NULL OR internal_invoice_number > 0);
                        END IF;
                    END $$;
                    """
                )
            )
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_invoices_internal_number ON invoices (document_type, point_of_sale, internal_invoice_number) WHERE internal_invoice_number IS NOT NULL"))
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_invoices_arca_number ON invoices (arca_environment, arca_cbte_tipo, arca_point_of_sale, arca_invoice_number) WHERE arca_invoice_number IS NOT NULL"))
            connection.execute(
                text(
                    """
                    INSERT INTO invoice_sequences (document_type, point_of_sale, next_number, created_at, updated_at)
                    SELECT document_type || '_INTERNAL', point_of_sale, COALESCE(MAX(internal_invoice_number), 0) + 1, now(), now()
                    FROM invoices
                    WHERE internal_invoice_number IS NOT NULL
                    GROUP BY document_type, point_of_sale
                    ON CONFLICT (document_type, point_of_sale) DO UPDATE
                    SET next_number = GREATEST(invoice_sequences.next_number, EXCLUDED.next_number),
                        updated_at = now()
                    """
                )
            )
        if self._table_exists(connection, "invoice_items"):
            item_fields = [
                ("iva_rate", "NUMERIC(5, 3)"),
                ("net_amount", "NUMERIC(12, 2)"),
                ("iva_amount", "NUMERIC(12, 2)"),
                ("fiscal_total", "NUMERIC(12, 2)"),
            ]
            for column_name, definition in item_fields:
                if not self._column_exists(connection, "invoice_items", column_name):
                    connection.execute(text(f"ALTER TABLE invoice_items ADD COLUMN {column_name} {definition}"))

        if not self._table_exists(connection, "invoice_tax_breakdown"):
            connection.execute(
                text(
                    """
                    CREATE TABLE invoice_tax_breakdown (
                        id BIGSERIAL PRIMARY KEY,
                        invoice_id BIGINT NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
                        iva_rate NUMERIC(5, 3) NOT NULL,
                        arca_iva_id INTEGER NOT NULL,
                        base_amount NUMERIC(12, 2) NOT NULL,
                        iva_amount NUMERIC(12, 2) NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL,
                        UNIQUE (invoice_id, iva_rate)
                    )
                    """
                )
            )

        if not self._table_exists(connection, "arca_requests"):
            connection.execute(
                text(
                    """
                    CREATE TABLE arca_requests (
                        id BIGSERIAL PRIMARY KEY,
                        invoice_id BIGINT NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
                        operation VARCHAR(80) NOT NULL,
                        environment VARCHAR(20) NOT NULL,
                        request_hash VARCHAR(64) NOT NULL,
                        sanitized_request JSONB NOT NULL,
                        sanitized_response JSONB,
                        status VARCHAR(20) NOT NULL,
                        error_code VARCHAR(50),
                        error_message TEXT,
                        created_at TIMESTAMPTZ NOT NULL
                    )
                    """
                )
            )

    def _drop_transport_redundancy(self, *, connection) -> None:
        if self._table_exists(connection, "customers"):
            connection.execute(text("ALTER TABLE customers DROP COLUMN IF EXISTS transport"))

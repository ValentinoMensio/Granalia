from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import Table, create_engine, select

from .postgres_bootstrap import PostgresBootstrapMixin
from .postgres_catalog import PostgresCatalogMixin
from .postgres_customers import PostgresCustomerMixin, PostgresTransportMixin
from .postgres_invoices import PostgresInvoiceMixin
from .postgres_migrations import PostgresMigrationMixin
from .postgres_schema import build_metadata
from .postgres_utils import default_profile, serialize_value, utc_now


class PostgresRepository(
    PostgresMigrationMixin,
    PostgresCatalogMixin,
    PostgresCustomerMixin,
    PostgresTransportMixin,
    PostgresInvoiceMixin,
    PostgresBootstrapMixin,
):
    catalogs: Table
    price_lists: Table
    transports: Table
    customers: Table
    products: Table
    product_offerings: Table
    invoices: Table
    invoice_items: Table
    app_users: Table

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.url = os.getenv(
            "GRANALIA_POSTGRES_URL",
            "postgresql+psycopg://granalia:granalia@127.0.0.1:5432/granalia",
        )
        self.engine = create_engine(self.url, future=True)
        with self.engine.connect() as connection:
            connection.execute(select(1))

        self.metadata, tables = build_metadata()
        for name, table in tables.items():
            setattr(self, name, table)


__all__ = ["PostgresRepository", "build_metadata", "default_profile", "serialize_value", "utc_now"]

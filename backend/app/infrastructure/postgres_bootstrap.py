from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.engine import Engine
from sqlalchemy.sql.schema import Table

from ..types import BootstrapPayloadData
from .postgres_protocol import PostgresRepositoryProtocol
from .postgres_utils import utc_now


class PostgresBootstrapMixin(PostgresRepositoryProtocol):
    engine: Engine
    catalogs: Table
    customers: Table
    url: str

    def _table_empty(self, table) -> bool:
        with self.engine.connect() as connection:
            count = connection.execute(select(table.c[list(table.c.keys())[0]]).limit(1)).first()
        return count is None

    def ensure_seeded(self) -> None:
        now = utc_now()
        with self.engine.begin() as connection:
            self._ensure_customer_billing_fields(connection=connection)
            self._ensure_fractional_invoice_quantities(connection=connection)
            self._ensure_price_list_invoice_fields(connection=connection)
            self._ensure_offering_net_weight(connection=connection)
            self._ensure_invoice_historical_snapshot_fields(connection=connection)
            self._ensure_arca_fiscal_base(connection=connection)

            active_catalog = connection.execute(
                select(self.catalogs.c.catalog).where(self.catalogs.c.active.is_(True)).order_by(self.catalogs.c.id.desc()).limit(1)
            ).scalar_one_or_none()
            if active_catalog:
                self._sync_catalog_tables(active_catalog, connection=connection, now=now)
                self._ensure_offering_net_weight(connection=connection)
                self._refresh_active_catalog_snapshot(connection=connection, now=now)

            if not self._table_empty(self.customers):
                self._sync_customer_references(connection=connection, now=now)

    def bootstrap_payload(self) -> BootstrapPayloadData:
        self.ensure_seeded()
        profiles = self.get_profiles_map()
        clients = sorted(profile["name"] for profile in profiles.values())
        try:
            catalog = self.get_active_catalog()
        except RuntimeError:
            catalog = []
        price_lists = self.list_price_lists()
        return {
            "catalog": catalog,
            "profiles": profiles,
            "clients": clients,
            "transports": self.get_transports(),
            "price_lists": price_lists,
            "price_list": self.get_active_price_list_meta(),
            "database": {
                "type": "postgresql",
                "url": make_url(self.url).render_as_string(hide_password=True),
            },
        }

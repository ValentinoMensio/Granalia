from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.engine import Engine
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.sql.schema import Table
from typing import cast

from ..core.utils import canonicalize_discount_config
from ..types import CustomerProfileData, TransportData
from .postgres_protocol import PostgresRepositoryProtocol
from .postgres_utils import default_profile, serialize_value, utc_now


class PostgresCustomerMixin(PostgresRepositoryProtocol):
    engine: Engine
    customers: Table
    transports: Table

    def _upsert_customer(self, customer: CustomerProfileData | dict[str, object], *, connection, now) -> int:
        customer_payload = dict(customer)
        customer_id = customer_payload.pop("id", None)

        if customer_id is None:
            stmt = insert(self.customers).values(**customer_payload).returning(self.customers.c.id)
            return int(connection.execute(stmt).scalar_one())

        result = connection.execute(
            update(self.customers)
            .where(self.customers.c.id == customer_id)
            .values(**customer_payload)
        )
        if result.rowcount == 0:
            raise ValueError("Cliente no encontrado")
        return int(str(customer_id))

    def get_profiles_map(self) -> dict[str, CustomerProfileData]:
        result: dict[str, CustomerProfileData] = {}
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(
                    self.customers,
                    self.transports.c.name.label("transport"),
                )
                .select_from(
                    self.customers.outerjoin(
                        self.transports,
                        self.customers.c.transport_id == self.transports.c.transport_id,
                    )
                )
                .order_by(self.customers.c.name)
            ).mappings().all()
        for row in rows:
            payload = cast(CustomerProfileData, {key: serialize_value(value) for key, value in row.items()})
            payload["transport"] = payload.get("transport") or ""
            _mode, payload["footer_discounts"], payload["line_discounts_by_format"] = canonicalize_discount_config(
                payload.get("footer_discounts"),
                payload.get("line_discounts_by_format"),
            )
            payload_id = payload.get("id")
            result[str(payload_id)] = cast(CustomerProfileData, payload)
        return result

    def get_customer(self, customer_id: int) -> CustomerProfileData | None:
        with self.engine.connect() as connection:
            row = connection.execute(
                select(
                    self.customers,
                    self.transports.c.name.label("transport"),
                )
                .select_from(
                    self.customers.outerjoin(
                        self.transports,
                        self.customers.c.transport_id == self.transports.c.transport_id,
                    )
                )
                .where(self.customers.c.id == customer_id)
            ).mappings().first()
        if not row:
            return None
        payload = cast(CustomerProfileData, {key: serialize_value(value) for key, value in row.items()})
        payload["transport"] = payload.get("transport") or ""
        _mode, payload["footer_discounts"], payload["line_discounts_by_format"] = canonicalize_discount_config(
            payload.get("footer_discounts"),
            payload.get("line_discounts_by_format"),
        )
        return cast(CustomerProfileData, payload)

    def save_profile(self, profile: CustomerProfileData | dict[str, object]) -> CustomerProfileData:
        now = utc_now()
        customer_id = profile.get("id")
        profile_name = str(profile.get("name") or "")
        existing = default_profile(profile_name)
        with self.engine.connect() as connection:
            row = None
            if customer_id is not None:
                row = connection.execute(select(self.customers).where(self.customers.c.id == customer_id)).mappings().first()
        if row:
            existing.update({k: serialize_value(v) for k, v in row.items()})
        merged: dict[str, object] = dict(existing)
        merged.update(profile)
        merged["name"] = profile.get("name") or existing.get("name") or ""
        merged["secondary_line"] = merged.get("secondary_line", "")
        merged["transport"] = merged.get("transport") or ""
        merged["notes"] = merged.get("notes", [])
        _mode, merged["footer_discounts"], merged["line_discounts_by_format"] = canonicalize_discount_config(
            merged.get("footer_discounts", []),
            merged.get("line_discounts_by_format", {}),
        )
        source_count_value = merged.get("source_count", 0)
        merged["source_count"] = int(str(source_count_value))
        created_at = row["created_at"] if row else now
        merged["updated_at"] = now
        with self.engine.begin() as connection:
            transport_name = str(merged.get("transport") or "")
            transport_id = self._resolve_transport_id(connection=connection, transport_name=transport_name, now=now)
            saved_id = self._upsert_customer(
                {
                    "id": customer_id,
                    "name": merged["name"],
                    "secondary_line": merged["secondary_line"],
                    "notes": merged["notes"],
                    "footer_discounts": merged["footer_discounts"],
                    "line_discounts_by_format": merged["line_discounts_by_format"],
                    "source_count": merged["source_count"],
                    "transport_id": transport_id,
                    "created_at": created_at,
                    "updated_at": merged["updated_at"],
                },
                connection=connection,
                now=now,
            )
            self._sync_customer_references(connection=connection, now=now)
            merged["id"] = saved_id
        merged["created_at"] = created_at
        merged.pop("mode", None)
        return cast(CustomerProfileData, serialize_value(merged))


class PostgresTransportMixin(PostgresRepositoryProtocol):
    engine: Engine
    transports: Table

    def get_transports(self) -> list[TransportData]:
        with self.engine.connect() as connection:
            rows = connection.execute(select(self.transports).order_by(self.transports.c.name)).mappings().all()
        payload: list[TransportData] = cast(list[TransportData], [{key: serialize_value(value) for key, value in row.items()} for row in rows])
        return payload

    def save_transport(self, name: str, notes: list[str] | None = None, transport_id: int | None = None) -> TransportData:
        now = utc_now()
        transport_name = str(name or "").strip()
        transport_notes = notes or []
        if not transport_name:
            raise ValueError("Nombre de transporte requerido")

        with self.engine.begin() as connection:
            if transport_id is None:
                row = connection.execute(
                    select(self.transports)
                    .where(self.transports.c.name == transport_name)
                    .order_by(self.transports.c.transport_id)
                    .limit(1)
                ).mappings().first()
                if row:
                    connection.execute(
                        update(self.transports)
                        .where(self.transports.c.transport_id == row["transport_id"])
                        .values(notes=transport_notes, updated_at=now)
                    )
                    row = connection.execute(
                        select(self.transports).where(self.transports.c.transport_id == row["transport_id"])
                    ).mappings().first()
                else:
                    row = connection.execute(
                        insert(self.transports)
                        .values(
                            name=transport_name,
                            notes=transport_notes,
                            created_at=now,
                            updated_at=now,
                        )
                        .returning(self.transports)
                    ).mappings().first()
            else:
                duplicate = connection.execute(
                    select(self.transports)
                    .where(
                        self.transports.c.name == transport_name,
                        self.transports.c.transport_id != transport_id,
                    )
                    .order_by(self.transports.c.transport_id)
                    .limit(1)
                ).mappings().first()
                if duplicate:
                    target_id = duplicate["transport_id"]
                    connection.execute(
                        update(self.customers)
                        .where(self.customers.c.transport_id == transport_id)
                        .values(transport_id=target_id, updated_at=now)
                    )
                    connection.execute(
                        update(self.invoices)
                        .where(self.invoices.c.transport_id == transport_id)
                        .values(transport_id=target_id, transport=transport_name)
                    )
                    connection.execute(
                        update(self.transports)
                        .where(self.transports.c.transport_id == target_id)
                        .values(notes=transport_notes, updated_at=now)
                    )
                    connection.execute(self.transports.delete().where(self.transports.c.transport_id == transport_id))
                    row = connection.execute(
                        select(self.transports).where(self.transports.c.transport_id == target_id)
                    ).mappings().first()
                    return cast(TransportData, serialize_value(row))

                result = connection.execute(
                    update(self.transports)
                    .where(self.transports.c.transport_id == transport_id)
                    .values(name=transport_name, notes=transport_notes, updated_at=now)
                )
                if result.rowcount == 0:
                    raise ValueError("Transporte no encontrado")
                row = connection.execute(
                    select(self.transports).where(self.transports.c.transport_id == transport_id)
                ).mappings().first()
        return cast(TransportData, serialize_value(row))

    def delete_transport(self, transport_id: int) -> None:
        with self.engine.begin() as connection:
            connection.execute(self.transports.delete().where(self.transports.c.transport_id == transport_id))

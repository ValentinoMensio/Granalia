from __future__ import annotations

import argparse
import os
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from math import gcd
from pathlib import Path

from sqlalchemy import MetaData, create_engine, select, update

from import_2026 import DEFAULT_POSTGRES_URL, DEFAULT_SOURCE_DIR, collect_source_files, parse_invoice, split_product_label


@dataclass(slots=True)
class BonusObservation:
    client_name: str
    product_name: str
    offering_label: str
    buy_quantity: int
    bonus_quantity: int
    source: Path


def connect_database():
    url = os.getenv("GRANALIA_POSTGRES_URL", DEFAULT_POSTGRES_URL)
    engine = create_engine(url, future=True)
    metadata = MetaData()
    metadata.reflect(bind=engine, only=["customers", "products", "product_offerings"])
    return engine, metadata.tables


def simplify_ratio(buy_quantity: int, bonus_quantity: int) -> tuple[int, int]:
    divisor = gcd(buy_quantity, bonus_quantity)
    return buy_quantity // divisor, bonus_quantity // divisor


def collect_bonus_observations(source_dir: Path) -> tuple[list[BonusObservation], int]:
    observations: list[BonusObservation] = []
    skipped = 0

    for path in collect_source_files(source_dir):
        try:
            invoice = parse_invoice(path)
        except Exception as exc:
            skipped += 1
            print(f"SKIP {path}: {exc}")
            continue

        paid_by_product: dict[tuple[str, str], int] = defaultdict(int)
        bonus_by_product: dict[tuple[str, str], int] = defaultdict(int)
        for item in invoice.items:
            product_name, offering_label = split_product_label(item.label)
            key = (product_name, offering_label)
            if item.unit_price == 0:
                bonus_by_product[key] += item.quantity
            else:
                paid_by_product[key] += item.quantity

        for key, bonus_quantity in bonus_by_product.items():
            paid_quantity = paid_by_product.get(key, 0)
            if paid_quantity <= 0 or bonus_quantity <= 0:
                continue
            buy_quantity, normalized_bonus = simplify_ratio(paid_quantity, bonus_quantity)
            observations.append(
                BonusObservation(
                    client_name=invoice.client_name,
                    product_name=key[0],
                    offering_label=key[1],
                    buy_quantity=buy_quantity,
                    bonus_quantity=normalized_bonus,
                    source=path,
                )
            )

    return observations, skipped


def choose_ratio(observations: list[BonusObservation]) -> tuple[int, int]:
    ratios = Counter((item.buy_quantity, item.bonus_quantity) for item in observations)
    return ratios.most_common(1)[0][0]


def build_product_indexes(connection, tables) -> tuple[dict[str, int], dict[tuple[str, str], int]]:
    products = connection.execute(select(tables["products"])).mappings().all()
    product_ids = {row["name"]: int(row["id"]) for row in products}
    offerings = connection.execute(
        select(
            tables["product_offerings"].c.id,
            tables["product_offerings"].c.product_id,
            tables["product_offerings"].c.label,
            tables["products"].c.name.label("product_name"),
        ).select_from(
            tables["product_offerings"].join(
                tables["products"],
                tables["product_offerings"].c.product_id == tables["products"].c.id,
            )
        )
    ).mappings().all()
    offering_ids = {(row["product_name"], row["label"]): int(row["id"]) for row in offerings}
    return product_ids, offering_ids


def build_rules_for_customer(
    observations: list[BonusObservation],
    product_ids: dict[str, int],
    offering_ids: dict[tuple[str, str], int],
) -> list[dict[str, int | None]]:
    buy_quantity, bonus_quantity = choose_ratio(observations)
    matching = [item for item in observations if (item.buy_quantity, item.bonus_quantity) == (buy_quantity, bonus_quantity)]
    product_offering_pairs = {(item.product_name, item.offering_label) for item in matching}

    if len(product_offering_pairs) >= 3:
        return [
            {
                "product_id": None,
                "offering_id": None,
                "buy_quantity": buy_quantity,
                "bonus_quantity": bonus_quantity,
            }
        ]

    rules = []
    for product_name, offering_label in sorted(product_offering_pairs):
        product_id = product_ids.get(product_name)
        offering_id = offering_ids.get((product_name, offering_label))
        if product_id is None or offering_id is None:
            continue
        rules.append(
            {
                "product_id": product_id,
                "offering_id": offering_id,
                "buy_quantity": buy_quantity,
                "bonus_quantity": bonus_quantity,
            }
        )
    return rules


def import_bonuses(source_dir: Path, dry_run: bool, replace: bool) -> None:
    observations, skipped = collect_bonus_observations(source_dir)
    by_customer: dict[str, list[BonusObservation]] = defaultdict(list)
    for observation in observations:
        by_customer[observation.client_name].append(observation)

    print(f"Bonificaciones detectadas: {len(observations)}; facturas omitidas: {skipped}; clientes con bonificación: {len(by_customer)}")
    if not observations:
        return

    engine, tables = connect_database()
    now = datetime.now(timezone.utc)
    updated = 0
    missing_customers = 0
    customers_without_rules = 0

    with engine.begin() as connection:
        product_ids, offering_ids = build_product_indexes(connection, tables)
        for client_name, customer_observations in sorted(by_customer.items()):
            customer = connection.execute(
                select(tables["customers"]).where(tables["customers"].c.name == client_name)
            ).mappings().first()
            if not customer:
                missing_customers += 1
                print(f"MISS cliente no encontrado: {client_name}")
                continue

            rules = build_rules_for_customer(customer_observations, product_ids, offering_ids)
            if not rules:
                customers_without_rules += 1
                print(f"MISS sin productos/formats en catálogo: {client_name}")
                continue

            existing_rules = customer.get("automatic_bonus_rules") or []
            next_rules = rules if replace else [*existing_rules, *rules]
            ratio = choose_ratio(customer_observations)
            scope = "global" if rules and rules[0]["product_id"] is None else f"{len(rules)} producto/formato"
            print(f"{client_name}: {ratio[1]} cada {ratio[0]} ({scope})")

            if dry_run:
                continue

            connection.execute(
                update(tables["customers"])
                .where(tables["customers"].c.id == customer["id"])
                .values(automatic_bonus_rules=next_rules, updated_at=now)
            )
            updated += 1

    if dry_run:
        print("Dry-run: no se escribieron cambios.")
    else:
        print(f"Bonificaciones insertadas en clientes: {updated}")
    if missing_customers:
        print(f"Clientes no encontrados: {missing_customers}")
    if customers_without_rules:
        print(f"Clientes sin regla por falta de producto/formato en catálogo: {customers_without_rules}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Infiere bonificaciones desde facturas 2026 y las inserta en clientes.")
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR, help="Carpeta con archivos .xlsx de 2026")
    parser.add_argument("--apply", action="store_true", help="Escribe cambios en PostgreSQL. Sin esto solo muestra dry-run.")
    parser.add_argument("--replace", action="store_true", help="Reemplaza reglas existentes en vez de agregarlas.")
    args = parser.parse_args()
    import_bonuses(args.source_dir.resolve(), dry_run=not args.apply, replace=args.replace)


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import select, text, update

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.infrastructure.postgres import PostgresRepository
from app.infrastructure.postgres_utils import utc_now


def normalize_id(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def merge_aliases(target_aliases: list[Any], source_names: list[str]) -> list[str]:
    aliases: list[str] = []
    seen: set[str] = set()
    for value in [*target_aliases, *source_names]:
        text_value = str(value or "").strip()
        if not text_value:
            continue
        key = text_value.casefold()
        if key in seen:
            continue
        seen.add(key)
        aliases.append(text_value)
    return aliases


def merge_catalog_products(catalog: list[dict[str, Any]], *, source_id: int, target_id: int, target_name: str, source_names: set[str], offering_id_by_label: dict[str, int]) -> list[dict[str, Any]]:
    next_catalog: list[dict[str, Any]] = []
    target_product: dict[str, Any] | None = None
    source_products: list[dict[str, Any]] = []

    for product in catalog or []:
        product_id = normalize_id(product.get("id"))
        product_name = str(product.get("name") or "").strip()
        if product_id == target_id:
            target_product = copy.deepcopy(product)
        elif product_id == source_id or product_name in source_names:
            source_products.append(copy.deepcopy(product))
        else:
            next_catalog.append(product)

    if target_product is None:
        if source_products:
            target_product = source_products.pop(0)
        else:
            return catalog

    target_product["id"] = target_id
    target_product["name"] = target_name
    target_offerings = {str(offering.get("label") or "").strip(): copy.deepcopy(offering) for offering in target_product.get("offerings", []) if str(offering.get("label") or "").strip()}

    for source_product in source_products:
        for offering in source_product.get("offerings", []) or []:
            label = str(offering.get("label") or "").strip()
            if not label or label in target_offerings:
                continue
            next_offering = copy.deepcopy(offering)
            if label in offering_id_by_label:
                next_offering["id"] = offering_id_by_label[label]
            target_offerings[label] = next_offering

    target_product["offerings"] = list(target_offerings.values())
    next_catalog.append(target_product)
    return next_catalog


def update_automatic_bonus_rules(rules: Any, *, source_id: int, target_id: int, offering_id_map: dict[int, int]) -> tuple[Any, bool]:
    if not isinstance(rules, list):
        return rules, False

    changed = False
    next_rules = copy.deepcopy(rules)
    for rule in next_rules:
        if not isinstance(rule, dict):
            continue
        if normalize_id(rule.get("product_id")) == source_id:
            rule["product_id"] = target_id
            changed = True
        offering_id = normalize_id(rule.get("offering_id"))
        if offering_id in offering_id_map:
            rule["offering_id"] = offering_id_map[offering_id]
            changed = True
    return next_rules, changed


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge one product into another, preserving invoice history and stats.")
    parser.add_argument("--source", type=int, required=True, help="Product ID to absorb/deactivate")
    parser.add_argument("--target", type=int, required=True, help="Product ID to keep")
    parser.add_argument("--execute", action="store_true", help="Apply changes. Without this flag the script only previews counts.")
    args = parser.parse_args()

    if args.source == args.target:
        raise SystemExit("source and target must be different")

    repository = PostgresRepository(Path.cwd())
    now = utc_now()

    with repository.engine.begin() as connection:
        source = connection.execute(select(repository.products).where(repository.products.c.id == args.source)).mappings().first()
        target = connection.execute(select(repository.products).where(repository.products.c.id == args.target)).mappings().first()
        if not source:
            raise SystemExit(f"source product {args.source} not found")
        if not target:
            raise SystemExit(f"target product {args.target} not found")

        source_offerings = connection.execute(select(repository.product_offerings).where(repository.product_offerings.c.product_id == args.source)).mappings().all()
        target_offerings = connection.execute(select(repository.product_offerings).where(repository.product_offerings.c.product_id == args.target)).mappings().all()
        target_offering_by_label = {str(row["label"]): row for row in target_offerings}
        offering_id_map = {
            int(source_offering["id"]): int(target_offering_by_label[str(source_offering["label"])]["id"])
            for source_offering in source_offerings
            if str(source_offering["label"]) in target_offering_by_label
        }
        source_names = [str(source["name"]), *[str(alias) for alias in (source.get("aliases") or [])]]

        invoice_items_to_update = connection.execute(
            select(repository.invoice_items.c.id).where(
                (repository.invoice_items.c.product_id == args.source)
                | (repository.invoice_items.c.product_name.in_(source_names))
            )
        ).all()
        customer_rows = connection.execute(select(repository.customers.c.id, repository.customers.c.automatic_bonus_rules)).mappings().all()
        customers_to_update = [
            row["id"]
            for row in customer_rows
            if update_automatic_bonus_rules(row["automatic_bonus_rules"], source_id=args.source, target_id=args.target, offering_id_map=offering_id_map)[1]
        ]
        catalog_rows = connection.execute(select(repository.catalogs.c.id, repository.catalogs.c.catalog)).mappings().all()

        print(f"Source: {args.source} - {source['name']}")
        print(f"Target: {args.target} - {target['name']}")
        print(f"Offering mappings: {offering_id_map}")
        print(f"Invoice items to update: {len(invoice_items_to_update)}")
        print(f"Customers with automatic bonus rules to update: {len(customers_to_update)}")
        print(f"Catalog snapshots to review: {len(catalog_rows)}")

        if not args.execute:
            print("Dry run only. Re-run with --execute to apply changes.")
            return

        for source_offering_id, target_offering_id in offering_id_map.items():
            connection.execute(
                update(repository.invoice_items)
                .where(repository.invoice_items.c.offering_id == source_offering_id)
                .values(offering_id=target_offering_id)
            )

        for target_offering in target_offerings:
            connection.execute(
                update(repository.invoice_items)
                .where(
                    ((repository.invoice_items.c.product_id == args.source) | (repository.invoice_items.c.product_name.in_(source_names))),
                    repository.invoice_items.c.offering_label == target_offering["label"],
                )
                .values(offering_id=int(target_offering["id"]))
            )

        connection.execute(
            update(repository.invoice_items)
            .where(
                (repository.invoice_items.c.product_id == args.source)
                | (repository.invoice_items.c.product_name.in_(source_names))
            )
            .values(product_id=args.target, product_name=str(target["name"]))
        )

        for row in customer_rows:
            next_rules, changed = update_automatic_bonus_rules(row["automatic_bonus_rules"], source_id=args.source, target_id=args.target, offering_id_map=offering_id_map)
            if changed:
                connection.execute(
                    update(repository.customers)
                    .where(repository.customers.c.id == row["id"])
                    .values(automatic_bonus_rules=next_rules, updated_at=now)
                )

        source_name_set = set(source_names)
        offering_id_by_label = {str(row["label"]): int(row["id"]) for row in target_offerings}
        for row in catalog_rows:
            next_catalog = merge_catalog_products(
                row["catalog"] or [],
                source_id=args.source,
                target_id=args.target,
                target_name=str(target["name"]),
                source_names=source_name_set,
                offering_id_by_label=offering_id_by_label,
            )
            connection.execute(
                update(repository.catalogs)
                .where(repository.catalogs.c.id == row["id"])
                .values(catalog=next_catalog, updated_at=now)
            )

        connection.execute(
            update(repository.products)
            .where(repository.products.c.id == args.target)
            .values(aliases=merge_aliases(target.get("aliases") or [], source_names), updated_at=now)
        )
        connection.execute(
            update(repository.product_offerings)
            .where(repository.product_offerings.c.product_id == args.source)
            .values(active=False, updated_at=now)
        )
        connection.execute(
            update(repository.products)
            .where(repository.products.c.id == args.source)
            .values(active=False, updated_at=now)
        )
        repository._refresh_active_catalog_snapshot(connection=connection, now=now)

        print("Merge applied successfully.")


if __name__ == "__main__":
    main()

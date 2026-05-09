from __future__ import annotations

from ..core.utils import derive_discount_mode, discount_key_for_label, is_x1kg_label, normalize_text
from ..domain.catalog import catalog_indexes
from ..domain.models import CatalogProduct, CustomerProfile, InvoiceRow, InvoiceSnapshot, InvoiceSummary, Order


def choose_rate(profile: CustomerProfile, discount_key: str) -> float:
    line_map = profile.line_discounts_by_format or {}
    if discount_key in line_map:
        return float(line_map[discount_key])
    return 0.0


def is_automatic_bonus_excluded(product_name: str, offering_label: str) -> bool:
    normalized_product = normalize_text(product_name)
    normalized_offering = normalize_text(offering_label)
    is_corn_flour = "maiz" in normalized_product and (
        "harina" in normalized_product or "h. maiz" in normalized_product or "h maiz" in normalized_product
    )
    is_one_kg = "1 kg" in normalized_offering or "1000" in normalized_offering
    return is_corn_flour and is_one_kg


def matching_automatic_bonus_rule(
    profile: CustomerProfile,
    product_id: int,
    offering_id: int,
    product_name: str,
    offering_label: str,
) -> object | None:
    if is_automatic_bonus_excluded(product_name, offering_label):
        return None

    best_rule = None
    best_score = -1
    for rule in profile.automatic_bonus_rules or []:
        product_matches = rule.product_id is None or int(rule.product_id) == int(product_id)
        if rule.offering_id is not None:
            offering_matches = int(rule.offering_id) == int(offering_id)
        elif rule.offering_label:
            offering_matches = normalize_text(rule.offering_label) in {
                normalize_text(offering_label),
                normalize_text(discount_key_for_label(offering_label)),
            }
        else:
            offering_matches = True
        if not product_matches or not offering_matches:
            continue
        score = (0 if rule.product_id is None else 1) + (0 if rule.offering_id is None and not rule.offering_label else 1)
        if score > best_score:
            best_rule = rule
            best_score = score
    return best_rule


def expand_rows(order: Order, profile: CustomerProfile, catalog: list[CatalogProduct]) -> list[InvoiceRow]:
    products_by_id, offerings_by_key, _aliases = catalog_indexes(catalog)
    rows: list[InvoiceRow] = []
    mode = derive_discount_mode(profile.to_data()["footer_discounts"], profile.line_discounts_by_format)
    for item in order.items:
        if not item.product_id or not item.offering_id:
            continue
        qty = float(item.quantity or 0)
        bonus_qty = int(item.bonus_quantity or 0)
        if qty <= 0 and bonus_qty <= 0:
            continue
        product_key = str(item.product_id)
        offering_key = (product_key, str(item.offering_id))
        product = products_by_id[product_key]
        offering = offerings_by_key[offering_key]
        if qty % 1 and not is_x1kg_label(offering["label"]):
            raise ValueError("Solo la presentación x 1 kg permite cantidades fraccionadas")
        if is_automatic_bonus_excluded(product["name"], offering["label"]):
            bonus_qty = 0
        else:
            matching_automatic_bonus_rule(profile, item.product_id, item.offering_id, product["name"], offering["label"])
        label = f"{product['name']} {offering['label']}"
        rate = choose_rate(profile, discount_key_for_label(offering["label"]))
        if bonus_qty > 0 and profile.automatic_bonus_disables_line_discount:
            rate = 0.0

        def append_row(quantity: float, unit_price: int, line_type: str) -> None:
            gross = round(quantity * unit_price)
            if mode in {"line_discount_net", "line_desc_factor"}:
                discount = round(gross * rate)
                total = gross - discount
            else:
                discount = 0
                total = gross
            rows.append(
                InvoiceRow(
                    item.product_id,
                    item.offering_id,
                    str(product["name"]),
                    str(offering["label"]),
                    float(offering.get("net_weight_kg") or 0),
                    line_type,
                    float(rate if line_type == "sale" else 0),
                    label,
                    quantity,
                    unit_price,
                    gross,
                    discount,
                    total,
                )
            )

        if qty > 0:
            unit_price = item.unit_price if item.unit_price is not None else int(offering["price"])
            append_row(qty, int(unit_price), "sale")
        if bonus_qty > 0:
            append_row(float(bonus_qty), 0, "bonus")
    return rows


def compute_summary(rows: list[InvoiceRow], profile: CustomerProfile) -> InvoiceSummary:
    gross_total = sum(int(item.gross) for item in rows)
    total_bultos = sum(float(item.quantity) for item in rows)
    mode = derive_discount_mode(profile.to_data()["footer_discounts"], profile.line_discounts_by_format)

    if mode in {"line_discount_net", "line_desc_factor"}:
        final_total = sum(int(item.total) for item in rows)
        discount_total = gross_total - final_total
    elif mode in {"summary_discount", "summary_multi_discount"}:
        running = gross_total
        for discount in profile.footer_discounts:
            running -= round(running * float(discount.rate))
        final_total = int(running)
        discount_total = gross_total - final_total
    else:
        final_total = gross_total
        discount_total = 0

    return InvoiceSummary(gross_total, discount_total, final_total, total_bultos)


def build_invoice_snapshot(order: Order, profile: CustomerProfile, catalog: list[CatalogProduct]) -> InvoiceSnapshot:
    rows = expand_rows(order, profile, catalog)
    if not rows:
        raise ValueError("No hay productos cargados")
    summary = compute_summary(rows, profile)
    return InvoiceSnapshot(rows=rows, summary=summary, order=order, profile=profile)

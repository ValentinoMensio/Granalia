from __future__ import annotations

import re
import unicodedata
from typing import Any

from ..types import FooterDiscountData


def normalize_text(value: Any) -> str:
    text = str(value or "").strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def clean_cell_text(value: Any) -> str:
    text = str(value or "").replace("\n", " ").strip()
    return re.sub(r"\s+", " ", text)


def parse_percent(text: str) -> float | None:
    match = re.search(r"(\d+(?:[\.,]\d+)?)\s*%", text or "")
    if not match:
        return None
    return float(match.group(1).replace(",", ".")) / 100.0


def parse_formula_multiplier(formula: Any) -> float | None:
    if not isinstance(formula, str) or not formula.startswith("="):
        return None
    matches = re.findall(r"\*(0?\.\d+|\d+\.\d+)", formula)
    if not matches:
        return None
    try:
        return float(matches[-1])
    except ValueError:
        return None


def discount_key_for_label(label: str) -> str:
    text = normalize_text(label)
    if "16x300" in text:
        return "Pack 300/350/400 gr"
    if "12x300" in text:
        return "Pack 300/350/400 gr"
    if "12x350" in text or "12x400" in text:
        return "Pack 300/350/400 gr"
    if "10x500" in text or "12x500" in text:
        return "Pack 500 gr"
    if "10x1 kg" in text or "10x1000" in text or "10x 1 kg" in text or "x 1 kg" in text or "x1 kg" in text:
        return "Pack 1 kg"
    if "x 4 kg" in text or "x4 kg" in text:
        return "Bolsa 4 kg"
    if "x 5 kg" in text or "x5 kg" in text:
        return "Bolsa 5 kg"
    if "x 25 kg" in text or "x25 kg" in text:
        return "Bolsa 25 kg"
    if "x 30 kg" in text or "x30 kg" in text:
        return "Bolsa 30 kg"
    return clean_cell_text(label) or "Otros"


def is_x1kg_label(label: str) -> bool:
    text = normalize_text(label)
    return "x 1 kg" in text or "x1 kg" in text or "x1kg" in text


def format_quantity(value: float | int) -> str:
    quantity = float(value or 0)
    if quantity.is_integer():
        return str(int(quantity))
    return f"{quantity:.2f}".rstrip("0").rstrip(".")


def safe_filename(value: str) -> str:
    text = clean_cell_text(value)
    text = re.sub(r"[\\/:*?\"<>|]", "-", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or "Pedido"


def normalize_footer_discounts(discounts: Any) -> list[FooterDiscountData]:
    normalized: list[FooterDiscountData] = []
    for discount in discounts or []:
        if not isinstance(discount, dict):
            continue
        try:
            rate = float(discount.get("rate") or 0)
        except (TypeError, ValueError):
            continue
        if rate <= 0:
            continue
        normalized.append(
            {
                "label": str(discount.get("label") or f"Dto {round(rate * 100, 2):g}%"),
                "rate": rate,
            }
        )
    return normalized


def normalize_line_discounts(line_map: Any) -> dict[str, float]:
    legacy_keys = {
        "pack12": "Pack 300/350/400 gr",
        "pack10_500": "Pack 500 gr",
        "pack10_1000": "Pack 1 kg",
        "bag4": "Bolsa 4 kg",
        "bag5": "Bolsa 5 kg",
        "bulk25": "Bolsa 25 kg",
        "bulk30": "Bolsa 30 kg",
        "12x400gr": "Pack 300/350/400 gr",
        "12x350gr": "Pack 300/350/400 gr",
        "12x300gr": "Pack 300/350/400 gr",
        "16x300gr": "Pack 300/350/400 gr",
        "10x500gr": "Pack 500 gr",
        "10x1000gr": "Pack 1 kg",
        "4kg": "Bolsa 4 kg",
        "5kg": "Bolsa 5 kg",
        "25kg": "Bolsa 25 kg",
        "30kg": "Bolsa 30 kg",
    }
    normalized: dict[str, float] = {}
    for key, value in (line_map or {}).items():
        raw_key = str(key).strip()
        if raw_key == "*":
            continue
        try:
            rate = float(value or 0)
        except (TypeError, ValueError):
            continue
        if rate > 0:
            mapped_key = legacy_keys.get(raw_key, raw_key)
            if mapped_key.lower() in {"unknown", "otros"}:
                continue
            normalized[mapped_key] = rate
    return normalized


def derive_discount_mode(footer_discounts: Any, line_discounts_by_format: Any) -> str:
    normalized_line = normalize_line_discounts(line_discounts_by_format)
    if normalized_line:
        return "line_discount_net"

    normalized_footer = normalize_footer_discounts(footer_discounts)
    if len(normalized_footer) > 1:
        return "summary_multi_discount"
    if len(normalized_footer) == 1:
        return "summary_discount"
    return "summary"


def canonicalize_discount_config(footer_discounts: Any, line_discounts_by_format: Any) -> tuple[str, list[FooterDiscountData], dict[str, float]]:
    normalized_footer = normalize_footer_discounts(footer_discounts)
    normalized_line = normalize_line_discounts(line_discounts_by_format)

    if normalized_line:
        return "line_discount_net", [], normalized_line

    if len(normalized_footer) > 1:
        return "summary_multi_discount", normalized_footer, {}
    if len(normalized_footer) == 1:
        return "summary_discount", normalized_footer, {}
    return "summary", [], {}

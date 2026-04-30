from __future__ import annotations

import re
from io import BytesIO
from typing import TypedDict

from pypdf import PdfReader

from ..core.utils import normalize_text
from ..domain.models import CatalogOffering, CatalogProduct


class ProductSpec(TypedDict):
    id: str
    formats: list[str]


PRODUCT_SPECS: dict[str, ProductSpec] = {
    "Arvejas Partidas": {"id": "arvejas_partidas", "formats": ["12x400", "10x500", "x5kg", "bulk"]},
    "Avena Arrollada x 300 gr": {"id": "avena_arrollada", "formats": ["16x300", "x4kg", "bulk"]},
    "Avena Instantánea x 350 gr": {"id": "avena_instantanea", "formats": ["12x350", "x4kg", "bulk"]},
    "Garbanzos": {"id": "garbanzos", "formats": ["12x400", "10x500", "x5kg", "bulk"]},
    "Harina de Maíz Cocción Rápida": {"id": "harina_maiz_coccion_rapida", "formats": ["10x500", "x5kg", "bulk"]},
    "Harina de Maíz": {"id": "harina_maiz", "formats": ["10x500", "10x1000", "x5kg", "bulk"]},
    "Harina de Maíz Blanca": {"id": "harina_maiz_blanca", "formats": ["10x1000"]},
    "Lentejas": {"id": "lentejas", "formats": ["12x400", "10x500", "x5kg", "bulk"]},
    "Maíz Pisingallo": {"id": "maiz_pisingallo", "formats": ["12x400", "10x500", "x5kg", "bulk"]},
    "Maíz Pisado Blanco": {"id": "maiz_pisado_blanco", "formats": ["12x400", "10x500", "x5kg", "bulk"]},
    "Porotos Alubia": {"id": "porotos_alubia", "formats": ["12x400", "10x500", "x5kg", "bulk"]},
    "Maíz Partido Colorado": {"id": "maiz_partido_colorado", "formats": ["10x500", "x5kg", "bulk"]},
    "Porotos Negros": {"id": "porotos_negros", "formats": ["12x400", "x5kg", "bulk"]},
    "Porotos Colorados": {"id": "porotos_colorados", "formats": ["12x400", "x5kg", "bulk"]},
    "Porotos Soja": {"id": "porotos_soja", "formats": ["10x500", "x5kg", "bulk_single"]},
    "Semola de Trigo": {"id": "semola_trigo", "formats": ["12x400", "10x500", "x5kg", "bulk"]},
    "Trigo Machacado Burgol": {"id": "trigo_burgol", "formats": ["12x400", "10x500", "x5kg", "bulk"]},
    "Trigo Pelado": {"id": "trigo_pelado", "formats": ["12x400", "10x500", "x5kg", "bulk"]},
    "Mijo": {"id": "mijo", "formats": ["10x500"]},
    "Alpiste": {"id": "alpiste", "formats": ["10x500"]},
    "Mezcla para Pájaros": {"id": "mezcla_pajaros", "formats": ["10x500"]},
    "Arvejas Enteras": {"id": "arvejas_enteras", "formats": ["x5kg", "bulk"]},
    "Arroz Parbolizado": {"id": "arroz_parbolizado", "formats": ["x5kg", "bulk"]},
    "Arroz Largo Fino 5/0": {"id": "arroz_largo_fino", "formats": ["x5kg", "bulk"]},
    "Arroz Integral Largo Fino": {"id": "arroz_integral", "formats": ["x5kg", "bulk"]},
    "Arroz Yamaní": {"id": "arroz_yamani", "formats": ["x5kg", "bulk"]},
    "Harina de Maíz Abatí": {"id": "harina_maiz_abati", "formats": ["x5kg", "bulk"]},
    "Harina de Garbanzos": {"id": "harina_garbanzos", "formats": ["x5kg", "bulk"]},
}

PRODUCT_NAME_ALIASES = {
    "Avena Arrollada": "Avena Arrollada x 300 gr",
    "Avena Instantánea": "Avena Instantánea x 350 gr",
    "H. Maíz Cocc. Rápida": "Harina de Maíz Cocción Rápida",
    "Maíz Partido Blanco": "Maíz Pisado Blanco",
    "Semola de Trigo": "Semola de Trigo",
    "Sémola de Trigo": "Semola de Trigo",
    "Trigo Burgol": "Trigo Machacado Burgol",
    "Arroz 5/0 Largo Fino": "Arroz Largo Fino 5/0",
}

PRODUCT_DISPLAY_NAMES = {
    "Maíz Pisado Blanco": "Maíz Partido Blanco",
    "Semola de Trigo": "Sémola de Trigo",
    "Trigo Machacado Burgol": "Trigo Burgol",
    "Arroz Largo Fino 5/0": "Arroz 5/0 Largo Fino",
    "Avena Arrollada x 300 gr": "Avena Arrollada",
    "Avena Instantánea x 350 gr": "Avena Instantánea",
}


def _extract_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_numbers(line: str) -> list[int]:
    return [int(value) for value in re.findall(r"\d+", line)]


def _net_weight_kg_for_label(label: str) -> float:
    text = label.lower().replace(" ", "")
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


def _build_offerings(formats: list[str], numbers: list[int]) -> list[CatalogOffering]:
    offerings: list[CatalogOffering] = []
    idx = 0
    x1kg_price: int | None = None

    def append_offering(id: str, label: str, price: int) -> None:
        if price > 0:
            offerings.append(CatalogOffering(id=id, label=label, price=price, net_weight_kg=_net_weight_kg_for_label(label)))

    def set_x1kg_price(price: int, *, preferred: bool = False) -> None:
        nonlocal x1kg_price
        if price > 0 and (x1kg_price is None or preferred):
            x1kg_price = price

    def price_per_kg(price: int, grams: int) -> int:
        return round(price * 1000 / grams)

    for fmt in formats:
        if fmt == "bulk":
            if idx >= len(numbers):
                continue
            price = numbers[idx]
            set_x1kg_price(price, preferred=True)
            append_offering("x25kg", "x 25 kg", price * 25)
            append_offering("x30kg", "x 30 kg", price * 30)
            idx += 1
            continue
        if fmt == "bulk_single":
            if idx >= len(numbers):
                continue
            price = numbers[idx]
            set_x1kg_price(price, preferred=True)
            append_offering("x25kg", "x 25 kg", price * 25)
            idx += 1
            continue
        if idx >= len(numbers):
            continue
        price = numbers[idx]
        idx += 1
        if fmt == "12x400":
            set_x1kg_price(price_per_kg(price, 400))
            append_offering("12x400", "12x400 gr", price * 12)
        elif fmt == "16x300":
            set_x1kg_price(price_per_kg(price, 300))
            append_offering("16x300", "16x300 gr", price * 16)
        elif fmt == "12x350":
            set_x1kg_price(price_per_kg(price, 350))
            append_offering("12x350", "12x350 gr", price * 12)
        elif fmt == "10x500":
            set_x1kg_price(price_per_kg(price, 500))
            append_offering("10x500", "10x500 gr", price * 10)
        elif fmt == "10x1000":
            set_x1kg_price(price, preferred=True)
            append_offering("10x1000", "10x1 kg", price * 10)
        elif fmt == "x4kg":
            set_x1kg_price(price, preferred=True)
            append_offering("x4kg", "x 4 kg", price * 4)
        elif fmt == "x5kg":
            set_x1kg_price(price, preferred=True)
            append_offering("x5kg", "x 5 kg", price * 5)
    if x1kg_price is not None:
        append_offering("x1kg", "x 1 kg", x1kg_price)
    return offerings


def build_catalog_from_pdf(pdf_bytes: bytes, current_catalog: list[CatalogProduct]) -> list[CatalogProduct]:
    text = _extract_text(pdf_bytes)
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]
    line_map: dict[str, list[int]] = {}

    ordered_names: list[str] = sorted(PRODUCT_SPECS, key=len, reverse=True)
    for line in lines:
        for product_name in ordered_names:
            if not line.startswith(product_name):
                continue
            remainder = line[len(product_name):]
            line_map[PRODUCT_SPECS[product_name]["id"]] = _extract_numbers(remainder)
            break

    catalog: list[CatalogProduct] = []
    used_spec_ids: set[str] = set()
    for product in current_catalog:
        spec: ProductSpec | None = None
        normalized_product_names = {
            normalize_text(product.name),
            *(normalize_text(alias) for alias in product.aliases),
        }
        for product_name, data in PRODUCT_SPECS.items():
            canonical_name = PRODUCT_NAME_ALIASES.get(product.name, product.name)
            if (
                normalize_text(product_name) in normalized_product_names
                or normalize_text(canonical_name) == normalize_text(product_name)
                or data["id"] == str(product.id)
            ):
                spec = data
                break
        if not spec:
            catalog.append(product)
            continue
        numbers = line_map.get(spec["id"])
        if not numbers:
            catalog.append(product)
            continue
        used_spec_ids.add(spec["id"])
        existing_by_label = {offering.label: offering for offering in product.offerings}
        next_offerings: list[CatalogOffering] = []
        for offering in _build_offerings(spec["formats"], numbers):
            previous = existing_by_label.get(offering.label)
            next_offerings.append(
                CatalogOffering(
                    id=previous.id if previous and isinstance(previous.id, int) else offering.id,
                    label=offering.label,
                    price=offering.price,
                    net_weight_kg=offering.net_weight_kg or (previous.net_weight_kg if previous else 0),
                )
            )
        catalog.append(CatalogProduct(id=product.id, name=product.name, aliases=list(product.aliases), offerings=next_offerings))

    for product_name, spec in PRODUCT_SPECS.items():
        if spec["id"] in used_spec_ids or spec["id"] not in line_map:
            continue
        offerings = _build_offerings(spec["formats"], line_map[spec["id"]])
        if not offerings:
            continue
        display_name = PRODUCT_DISPLAY_NAMES.get(product_name, product_name)
        aliases = [] if display_name == product_name else [product_name]
        catalog.append(CatalogProduct(id=spec["id"], name=display_name, aliases=aliases, offerings=offerings))

    for idx, product in enumerate(catalog):
        if product.id in used_spec_ids:
            product_display = PRODUCT_DISPLAY_NAMES.get(product.name, product.name)
            if product_display != product.name:
                catalog[idx] = CatalogProduct(id=product.id, name=product_display, aliases=product.aliases, offerings=product.offerings)

    return catalog

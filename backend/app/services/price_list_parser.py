from __future__ import annotations

import re
from io import BytesIO
from typing import TypedDict

from pypdf import PdfReader

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
    "Porotos Negros": {"id": "porotos_negros", "formats": ["10x500", "x5kg", "bulk"]},
    "Porotos Colorados": {"id": "porotos_colorados", "formats": ["10x500", "x5kg", "bulk"]},
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


def _extract_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_numbers(line: str) -> list[int]:
    return [int(value) for value in re.findall(r"\d+", line)]


def _build_offerings(formats: list[str], numbers: list[int]) -> list[CatalogOffering]:
    offerings: list[CatalogOffering] = []
    idx = 0
    for fmt in formats:
        if fmt == "bulk":
            if idx >= len(numbers):
                continue
            price = numbers[idx]
            offerings.append(CatalogOffering(id="x25kg", label="x 25 kg", price=price * 25))
            offerings.append(CatalogOffering(id="x30kg", label="x 30 kg", price=price * 30))
            idx += 1
            continue
        if fmt == "bulk_single":
            if idx >= len(numbers):
                continue
            price = numbers[idx]
            offerings.append(CatalogOffering(id="x25kg", label="x 25 kg", price=price * 25))
            idx += 1
            continue
        if idx >= len(numbers):
            continue
        price = numbers[idx]
        idx += 1
        if fmt == "12x400":
            offerings.append(CatalogOffering(id="12x400", label="12x400 gr", price=price * 12))
        elif fmt == "16x300":
            offerings.append(CatalogOffering(id="16x300", label="16x300 gr", price=price * 16))
        elif fmt == "12x350":
            offerings.append(CatalogOffering(id="12x350", label="12x350 gr", price=price * 12))
        elif fmt == "10x500":
            offerings.append(CatalogOffering(id="10x500", label="10x500 gr", price=price * 10))
        elif fmt == "10x1000":
            offerings.append(CatalogOffering(id="10x1000", label="10x1 kg", price=price * 10))
        elif fmt == "x4kg":
            offerings.append(CatalogOffering(id="x4kg", label="x 4 kg", price=price * 4))
        elif fmt == "x5kg":
            offerings.append(CatalogOffering(id="x5kg", label="x 5 kg", price=price * 5))
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
    for product in current_catalog:
        spec: ProductSpec | None = None
        for product_name, data in PRODUCT_SPECS.items():
            if product_name == product.name or data["id"] == str(product.id):
                spec = data
                break
        if not spec:
            catalog.append(product)
            continue
        numbers = line_map.get(spec["id"])
        if not numbers:
            catalog.append(product)
            continue
        existing_by_label = {offering.label: offering for offering in product.offerings}
        next_offerings: list[CatalogOffering] = []
        for offering in _build_offerings(spec["formats"], numbers):
            previous = existing_by_label.get(offering.label)
            next_offerings.append(
                CatalogOffering(
                    id=previous.id if previous and isinstance(previous.id, int) else offering.id,
                    label=offering.label,
                    price=offering.price,
                )
            )
        catalog.append(CatalogProduct(id=product.id, name=product.name, aliases=list(product.aliases), offerings=next_offerings))
    return catalog

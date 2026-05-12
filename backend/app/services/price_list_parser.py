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


class PriceListImportWarning(TypedDict):
    product_id: int | str
    product_name: str
    offering_label: str | None
    kind: str
    message: str


class PriceListParseResult(TypedDict):
    catalog: list[CatalogProduct]
    warnings: list[PriceListImportWarning]


PRODUCT_SPECS: dict[str, ProductSpec] = {
    "Arvejas Partidas": {"id": "arvejas_partidas", "formats": ["12x400", "10x500", "x5kg", "bulk"]},
    "Avena Arrollada x 300 gr": {"id": "avena_arrollada", "formats": ["16x300", "x4kg", "bulk"]},
    "Avena Instantánea x 350 gr": {"id": "avena_instantanea", "formats": ["16x300", "x4kg", "bulk"]},
    "Garbanzos": {"id": "garbanzos", "formats": ["12x400", "10x500", "x5kg", "bulk"]},
    "Harina de Maíz Cocción Rápida": {"id": "harina_maiz_coccion_rapida", "formats": ["10x500", "x5kg", "bulk"]},
    "Harina de Maíz": {"id": "harina_maiz", "formats": ["10x500", "10x1000", "x5kg", "bulk"]},
    "Harina de Maíz Blanca": {"id": "harina_maiz_blanca", "formats": ["10x1000"]},
    "Lentejas": {"id": "lentejas", "formats": ["12x400", "10x500", "x5kg", "bulk"]},
    "Maíz Pisingallo": {"id": "maiz_pisingallo", "formats": ["12x400", "10x500", "x5kg", "bulk"]},
    "Maíz Pisado Blanco": {"id": "maiz_pisado_blanco", "formats": ["12x400", "10x500", "x5kg", "bulk"]},
    "Porotos Alubia": {"id": "porotos_alubia", "formats": ["12x400", "10x500", "x5kg", "bulk"]},
    "Maíz Partido Colorado": {"id": "maiz_partido_colorado", "formats": ["12x400", "x5kg", "bulk"]},
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


def _spec_id_for_product(product: CatalogProduct) -> str | None:
    normalized_product_names = {
        normalize_text(product.name),
        *(normalize_text(alias) for alias in product.aliases),
    }
    canonical_name = PRODUCT_NAME_ALIASES.get(product.name, product.name)
    for product_name, data in PRODUCT_SPECS.items():
        if (
            normalize_text(product_name) in normalized_product_names
            or normalize_text(canonical_name) == normalize_text(product_name)
            or data["id"] == str(product.id)
        ):
            return data["id"]
    return None


def _sort_catalog_by_import_order(catalog: list[CatalogProduct], detected_order: list[str]) -> list[CatalogProduct]:
    default_order = [spec["id"] for spec in PRODUCT_SPECS.values()]
    ordered_ids = [*detected_order, *(spec_id for spec_id in default_order if spec_id not in detected_order)]
    order_index = {spec_id: index for index, spec_id in enumerate(ordered_ids)}
    return [
        product
        for _index, product in sorted(
            enumerate(catalog),
            key=lambda item: (order_index.get(_spec_id_for_product(item[1]) or "", len(order_index)), item[0]),
        )
    ]


def _x1kg_price_from_offerings(offerings: list[CatalogOffering]) -> int | None:
    existing_x1kg = next((offering.price for offering in offerings if normalize_text(offering.label) in {"x 1 kg", "x1 kg", "x1kg"} and offering.price > 0), None)
    if existing_x1kg is not None:
        return existing_x1kg

    for offering in offerings:
        if offering.price > 0 and offering.net_weight_kg > 0:
            return round(offering.price / offering.net_weight_kg)
    return None


def _ensure_x1kg_offering(product: CatalogProduct, warnings: list[PriceListImportWarning]) -> CatalogProduct:
    if any(normalize_text(offering.label) in {"x 1 kg", "x1 kg", "x1kg"} for offering in product.offerings):
        return product

    price = _x1kg_price_from_offerings(product.offerings)
    if price is None:
        warnings.append(
            {
                "product_id": product.id,
                "product_name": product.name,
                "offering_label": "x 1 kg",
                "kind": "missing_x1kg",
                "message": "No se pudo calcular el precio x 1 kg porque no hay presentaciones con peso neto.",
            }
        )
        return product

    warnings.append(
        {
            "product_id": product.id,
            "product_name": product.name,
            "offering_label": "x 1 kg",
            "kind": "generated_x1kg",
            "message": "Se agregó x 1 kg calculado desde otra presentación; revisar antes de guardar.",
        }
    )
    return CatalogProduct(
        id=product.id,
        name=product.name,
        aliases=list(product.aliases),
        offerings=[*product.offerings, CatalogOffering(id="x1kg", label="x 1 kg", price=price, net_weight_kg=1)],
        iva_rate=product.iva_rate,
    )


def build_catalog_preview_from_pdf(pdf_bytes: bytes, current_catalog: list[CatalogProduct]) -> PriceListParseResult:
    text = _extract_text(pdf_bytes)
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]
    line_map: dict[str, list[int]] = {}
    detected_order: list[str] = []
    warnings: list[PriceListImportWarning] = []

    ordered_names: list[str] = sorted(PRODUCT_SPECS, key=len, reverse=True)
    for line in lines:
        for product_name in ordered_names:
            if not line.startswith(product_name):
                continue
            remainder = line[len(product_name):]
            spec_id = PRODUCT_SPECS[product_name]["id"]
            line_map[spec_id] = _extract_numbers(remainder)
            if spec_id not in detected_order:
                detected_order.append(spec_id)
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
            catalog.append(_ensure_x1kg_offering(product, warnings))
            continue
        numbers = line_map.get(spec["id"])
        if not numbers:
            warnings.append(
                {
                    "product_id": product.id,
                    "product_name": product.name,
                    "offering_label": None,
                    "kind": "product_missing_in_pdf",
                    "message": "Producto no detectado en el PDF; se conserva con sus precios anteriores.",
                }
            )
            catalog.append(_ensure_x1kg_offering(product, warnings))
            continue
        used_spec_ids.add(spec["id"])
        existing_by_label = {offering.label: offering for offering in product.offerings}
        next_offerings: list[CatalogOffering] = []
        updated_labels: set[str] = set()
        for offering in _build_offerings(spec["formats"], numbers):
            previous = existing_by_label.get(offering.label)
            updated_labels.add(offering.label)
            next_offerings.append(
                CatalogOffering(
                    id=previous.id if previous and isinstance(previous.id, int) else offering.id,
                    label=offering.label,
                    price=offering.price,
                    net_weight_kg=offering.net_weight_kg or (previous.net_weight_kg if previous else 0),
                )
            )
        for previous in product.offerings:
            if previous.label not in updated_labels:
                warnings.append(
                    {
                        "product_id": product.id,
                        "product_name": product.name,
                        "offering_label": previous.label,
                        "kind": "offering_missing_in_pdf",
                        "message": "Presentación no detectada en el PDF; se conserva con el precio anterior.",
                    }
                )
                next_offerings.append(previous)
        catalog.append(_ensure_x1kg_offering(CatalogProduct(id=product.id, name=product.name, aliases=list(product.aliases), offerings=next_offerings, iva_rate=product.iva_rate), warnings))

    for product_name, spec in PRODUCT_SPECS.items():
        if spec["id"] in used_spec_ids or spec["id"] not in line_map:
            continue
        offerings = _build_offerings(spec["formats"], line_map[spec["id"]])
        if not offerings:
            continue
        display_name = PRODUCT_DISPLAY_NAMES.get(product_name, product_name)
        aliases = [] if display_name == product_name else [product_name]
        catalog.append(_ensure_x1kg_offering(CatalogProduct(id=spec["id"], name=display_name, aliases=aliases, offerings=offerings), warnings))

    for idx, product in enumerate(catalog):
        if product.id in used_spec_ids:
            product_display = PRODUCT_DISPLAY_NAMES.get(product.name, product.name)
            if product_display != product.name:
                catalog[idx] = CatalogProduct(id=product.id, name=product_display, aliases=product.aliases, offerings=product.offerings, iva_rate=product.iva_rate)

    return {"catalog": _sort_catalog_by_import_order(catalog, detected_order), "warnings": warnings}


def build_catalog_from_pdf(pdf_bytes: bytes, current_catalog: list[CatalogProduct]) -> list[CatalogProduct]:
    return build_catalog_preview_from_pdf(pdf_bytes, current_catalog)["catalog"]

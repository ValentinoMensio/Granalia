from __future__ import annotations

import argparse
import json
import math
from datetime import date, timedelta
from pathlib import Path

from app.infrastructure.postgres import PostgresRepository
from app.services.invoicing import generate_invoice_document


EMITTER_CUIT = "30712345678"
ARCA_ENVIRONMENT = "homologacion"
ARCA_POINT_OF_SALE = 1


def minimal_pdf_bytes(title: str) -> bytes:
    body = f"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>
endobj
4 0 obj
<< /Length 76 >>
stream
BT
/F1 18 Tf
72 770 Td
({title}) Tj
0 -28 Td
/F1 11 Tf
(Granalia demo seed) Tj
ET
endstream
endobj
5 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
xref
0 6
0000000000 65535 f 
0000000010 00000 n 
0000000063 00000 n 
0000000122 00000 n 
0000000248 00000 n 
0000000375 00000 n 
trailer
<< /Size 6 /Root 1 0 R >>
startxref
455
%%EOF
"""
    return body.encode("latin-1")


def normalize_lookup(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def find_catalog_product(catalog: list[dict[str, object]], product_id: int | None = None, product_name: str = "") -> dict[str, object] | None:
    if product_id is not None:
        match = next((item for item in catalog if str(item.get("id")) == str(product_id)), None)
        if match:
            return match
    normalized_name = normalize_lookup(product_name)
    return next((item for item in catalog if normalize_lookup(item.get("name")) == normalized_name), None)


def find_catalog_offering(product: dict[str, object] | None, offering_id: int | None = None, offering_label: str = "") -> dict[str, object] | None:
    if not product:
        return None
    offerings = product.get("offerings", [])
    if offering_id is not None:
        match = next((item for item in offerings if str(item.get("id")) == str(offering_id)), None)
        if match:
            return match
    normalized_label = normalize_lookup(offering_label)
    return next((item for item in offerings if normalize_lookup(item.get("label")) == normalized_label), None)


def split_quantity(value: object, declared_percentage: float) -> tuple[int, int]:
    quantity = float(value or 0)
    if quantity < 0 or not quantity.is_integer():
        raise ValueError("El modo dividido solo acepta cantidades enteras")
    declared_quantity = math.ceil(quantity * declared_percentage / 100)
    return int(quantity) - declared_quantity, declared_quantity


def order_with_items(order: dict[str, object], *, price_list_id: int | None, declared: bool, items: list[dict[str, object]]) -> dict[str, object]:
    return {
        **order,
        "price_list_id": price_list_id,
        "declared": declared,
        "items": items,
    }


def fiscalize_snapshot(snapshot: dict[str, object], catalog: list[dict[str, object]]) -> dict[str, object]:
    products_by_id = {str(product.get("id")): product for product in catalog}
    rows = []
    for row in snapshot.get("rows", []):
        next_row = dict(row)
        if row.get("product_id") is None and row.get("iva_rate") is not None:
            rows.append(next_row)
            continue
        product = products_by_id.get(str(row.get("product_id") or ""))
        if not product:
            raise ValueError(f"Producto fiscal no encontrado para {row.get('product_name') or row.get('label')}")
        iva_rate = product.get("iva_rate")
        if iva_rate is None:
            raise ValueError(f"Falta configurar IVA fiscal para {product.get('name')}")
        next_row["iva_rate"] = float(iva_rate)
        rows.append(next_row)
    return {**snapshot, "rows": rows}


def build_split_orders(order: dict[str, object], internal_catalog: list[dict[str, object]], fiscal_catalog: list[dict[str, object]]) -> tuple[dict[str, object], dict[str, object]]:
    declared_percentage = float(order.get("declared_percentage") or 0)
    internal_items: list[dict[str, object]] = []
    fiscal_items: list[dict[str, object]] = []

    for item in order.get("items", []):
        product = find_catalog_product(internal_catalog, item.get("product_id"))
        offering = find_catalog_offering(product, item.get("offering_id"))
        if not product or not offering:
            raise ValueError("Producto o presentacion interna no encontrada")

        fiscal_product = find_catalog_product(fiscal_catalog, product_name=str(product.get("name") or ""))
        fiscal_offering = find_catalog_offering(fiscal_product, offering_label=str(offering.get("label") or ""))
        if not fiscal_product:
            raise ValueError(f"Falta el producto {product.get('name')} en la lista declarada")
        if not fiscal_offering:
            raise ValueError(f"Falta la presentacion {offering.get('label')} de {product.get('name')} en la lista declarada")
        if fiscal_product.get("iva_rate") is None:
            raise ValueError(f"Falta configurar IVA fiscal para {fiscal_product.get('name')}")

        internal_quantity, fiscal_quantity = split_quantity(item.get("quantity"), declared_percentage)
        internal_bonus = int(item.get("bonus_quantity") or 0)
        if internal_quantity > 0 or internal_bonus > 0:
            internal_items.append({**item, "quantity": internal_quantity, "bonus_quantity": internal_bonus})
        if fiscal_quantity > 0:
            fiscal_items.append(
                {
                    **item,
                    "product_id": int(fiscal_product["id"]),
                    "offering_id": int(fiscal_offering["id"]),
                    "quantity": fiscal_quantity,
                    "bonus_quantity": 0,
                    "unit_price": int(fiscal_offering.get("price") or 0),
                }
            )

    if not internal_items and not fiscal_items:
        raise ValueError("No hay cantidades para generar")
    return (
        order_with_items(order, price_list_id=order.get("internal_price_list_id") or order.get("price_list_id"), declared=False, items=internal_items),
        order_with_items(order, price_list_id=order.get("fiscal_price_list_id"), declared=True, items=fiscal_items),
    )


def base_catalog_template() -> list[dict[str, object]]:
    return [
        {
            "id": "avena-arrollada",
            "name": "Avena Arrollada",
            "aliases": ["Avena", "Avena tradicional"],
            "iva_rate": 0.105,
            "offerings": [
                {"id": "avena-25", "label": "Bolsa 25 kg", "price": 22900, "net_weight_kg": 25},
                {"id": "avena-10", "label": "Bolsa 10 kg", "price": 9800, "net_weight_kg": 10},
                {"id": "avena-1", "label": "x 1 kg", "price": 1180, "net_weight_kg": 1},
            ],
        },
        {
            "id": "maiz-pisingallo",
            "name": "Maiz Pisingallo",
            "aliases": ["Pisingallo", "Pop corn"],
            "iva_rate": 0.105,
            "offerings": [
                {"id": "pisingallo-25", "label": "Bolsa 25 kg", "price": 26700, "net_weight_kg": 25},
                {"id": "pisingallo-5", "label": "x 5 kg", "price": 6120, "net_weight_kg": 5},
                {"id": "pisingallo-1", "label": "x 1 kg", "price": 1460, "net_weight_kg": 1},
            ],
        },
        {
            "id": "lenteja-turca",
            "name": "Lenteja Turca",
            "aliases": ["Lenteja", "Lenteja seca"],
            "iva_rate": 0.105,
            "offerings": [
                {"id": "lenteja-25", "label": "Bolsa 25 kg", "price": 31800, "net_weight_kg": 25},
                {"id": "lenteja-5", "label": "x 5 kg", "price": 7440, "net_weight_kg": 5},
                {"id": "lenteja-1", "label": "x 1 kg", "price": 1680, "net_weight_kg": 1},
            ],
        },
        {
            "id": "garbanzo-kabuli",
            "name": "Garbanzo Kabuli",
            "aliases": ["Garbanzo", "Garbanzo grande"],
            "iva_rate": 0.105,
            "offerings": [
                {"id": "garbanzo-25", "label": "Bolsa 25 kg", "price": 34400, "net_weight_kg": 25},
                {"id": "garbanzo-10", "label": "Bolsa 10 kg", "price": 14300, "net_weight_kg": 10},
                {"id": "garbanzo-1", "label": "x 1 kg", "price": 1820, "net_weight_kg": 1},
            ],
        },
        {
            "id": "poroto-alubia",
            "name": "Poroto Alubia",
            "aliases": ["Alubia", "Poroto blanco"],
            "iva_rate": 0.105,
            "offerings": [
                {"id": "alubia-25", "label": "Bolsa 25 kg", "price": 33600, "net_weight_kg": 25},
                {"id": "alubia-5", "label": "x 5 kg", "price": 7810, "net_weight_kg": 5},
                {"id": "alubia-1", "label": "x 1 kg", "price": 1760, "net_weight_kg": 1},
            ],
        },
        {
            "id": "trigo-burgol",
            "name": "Trigo Burgol Grueso",
            "aliases": ["Burgol", "Trigo partido"],
            "iva_rate": 0.21,
            "offerings": [
                {"id": "burgol-25", "label": "Bolsa 25 kg", "price": 30100, "net_weight_kg": 25},
                {"id": "burgol-5", "label": "x 5 kg", "price": 7020, "net_weight_kg": 5},
                {"id": "burgol-1", "label": "x 1 kg", "price": 1590, "net_weight_kg": 1},
            ],
        },
        {
            "id": "harina-maiz",
            "name": "Harina de Maiz Precocida",
            "aliases": ["Harina de maiz", "Polenta instantanea"],
            "iva_rate": 0.21,
            "offerings": [
                {"id": "h-maiz-20", "label": "Bolsa 20 kg", "price": 24800, "net_weight_kg": 20},
                {"id": "h-maiz-5", "label": "x 5 kg", "price": 6690, "net_weight_kg": 5},
                {"id": "h-maiz-1", "label": "x 1 kg", "price": 1490, "net_weight_kg": 1},
            ],
        },
        {
            "id": "arroz-integral",
            "name": "Arroz Integral Largo Fino",
            "aliases": ["Arroz integral", "Integral largo fino"],
            "iva_rate": 0.105,
            "offerings": [
                {"id": "arroz-25", "label": "Bolsa 25 kg", "price": 35700, "net_weight_kg": 25},
                {"id": "arroz-5", "label": "x 5 kg", "price": 8220, "net_weight_kg": 5},
                {"id": "arroz-1", "label": "x 1 kg", "price": 1890, "net_weight_kg": 1},
            ],
        },
    ]


def fiscal_catalog_from_internal(catalog: list[dict[str, object]]) -> list[dict[str, object]]:
    fiscal_catalog: list[dict[str, object]] = []
    for product in catalog:
        offerings = []
        for offering in product.get("offerings", []):
            price = int(offering.get("price") or 0)
            offerings.append(
                {
                    "id": offering["id"],
                    "label": offering["label"],
                    "price": round(price * 1.12),
                    "net_weight_kg": float(offering.get("net_weight_kg") or 0),
                }
            )
        fiscal_catalog.append(
            {
                "id": product["id"],
                "name": product["name"],
                "aliases": list(product.get("aliases") or []),
                "iva_rate": float(product.get("iva_rate") or 0.105),
                "offerings": offerings,
            }
        )
    return fiscal_catalog


def catalog_item(catalog: list[dict[str, object]], product_name: str, offering_label: str) -> tuple[dict[str, object], dict[str, object]]:
    for product in catalog:
        if str(product.get("name")) != product_name:
            continue
        for offering in product.get("offerings", []):
            if str(offering.get("label")) == offering_label:
                return product, offering
    raise ValueError(f"No se encontro {product_name} / {offering_label} en el catalogo")


def order_item(catalog: list[dict[str, object]], product_name: str, offering_label: str, *, quantity: float, bonus_quantity: int = 0) -> dict[str, object]:
    product, offering = catalog_item(catalog, product_name, offering_label)
    return {
        "product_id": int(product["id"]),
        "offering_id": int(offering["id"]),
        "offering_label": str(offering["label"]),
        "quantity": quantity,
        "bonus_quantity": bonus_quantity,
        "unit_price": int(offering.get("price") or 0),
    }


def make_profile(name: str, *, cuit: str, address: str, business_name: str, email: str, transport: str, secondary_line: str = "", notes: list[str] | None = None, footer_discounts: list[dict[str, object]] | None = None, line_discounts_by_format: dict[str, float] | None = None, automatic_bonus_rules: list[dict[str, object]] | None = None, iva_condition: str = "IVA Responsable Inscripto") -> dict[str, object]:
    return {
        "name": name,
        "cuit": cuit,
        "address": address,
        "business_name": business_name,
        "email": email,
        "iva_condition": iva_condition,
        "secondary_line": secondary_line,
        "transport": transport,
        "notes": notes or [],
        "footer_discounts": footer_discounts or [],
        "line_discounts_by_format": line_discounts_by_format or {},
        "automatic_bonus_rules": automatic_bonus_rules or [],
        "automatic_bonus_disables_line_discount": False,
        "source_count": 1,
    }


def make_order(profile: dict[str, object], *, when: date, price_list_id: int, items: list[dict[str, object]], notes: list[str], billing_mode: str = "internal_only", declared: bool = False, declared_percentage: float | None = None, fiscal_price_list_id: int | None = None) -> dict[str, object]:
    order = {
        "client_name": str(profile["name"]),
        "date": when.isoformat(),
        "price_list_id": price_list_id,
        "billing_mode": billing_mode,
        "declared": declared,
        "secondary_line": str(profile.get("secondary_line") or ""),
        "transport": str(profile.get("transport") or ""),
        "notes": notes,
        "items": items,
    }
    if declared_percentage is not None:
        order["declared_percentage"] = declared_percentage
        order["internal_price_list_id"] = price_list_id
    if fiscal_price_list_id is not None:
        order["fiscal_price_list_id"] = fiscal_price_list_id
    return order


def create_internal_invoice(repository: PostgresRepository, profile: dict[str, object], order: dict[str, object], catalog: list[dict[str, object]]) -> int:
    snapshot = generate_invoice_document(order, profile, catalog)
    return repository.save_invoice(order, profile, snapshot, update_customer=True, split_kind="internal", fiscal_status="internal")


def create_fiscal_invoice(repository: PostgresRepository, profile: dict[str, object], order: dict[str, object], catalog: list[dict[str, object]], *, document_type: str = "FACTURA", related_invoice_id: int | None = None, credit_reason: str = "") -> int:
    snapshot = generate_invoice_document(order, profile, catalog)
    snapshot = fiscalize_snapshot(snapshot, catalog)
    return repository.save_invoice(
        order,
        profile,
        snapshot,
        update_customer=True,
        split_kind="fiscal",
        fiscal_status="draft",
        document_type=document_type,
        related_invoice_id=related_invoice_id,
        credit_reason=credit_reason,
    )


def simulate_arca_status(repository: PostgresRepository, invoice_id: int, *, fiscal_status: str, customer_cuit: str, invoice_number: int | None = None, cbte_tipo: int = 1, error_message: str | None = None) -> None:
    arca_request_id = repository.create_arca_request(
        invoice_id=invoice_id,
        operation="FECAESolicitar",
        environment=ARCA_ENVIRONMENT,
        sanitized_request={
            "seed": True,
            "invoice_id": invoice_id,
            "cbte_tipo": cbte_tipo,
            "doc_nro": customer_cuit,
        },
        status="pending",
    )

    response_payload: dict[str, object] = {"seed": True, "invoice_id": invoice_id, "status": fiscal_status}
    if fiscal_status == "authorized":
        repository.update_arca_request(
            arca_request_id,
            status="authorized",
            sanitized_response={**response_payload, "cae": f"6110000{invoice_id:06d}", "invoice_number": invoice_number},
        )
        repository.update_invoice_arca_status(
            invoice_id,
            fiscal_status="authorized",
            arca_environment=ARCA_ENVIRONMENT,
            arca_cuit_emisor=EMITTER_CUIT,
            arca_cbte_tipo=cbte_tipo,
            arca_concepto=1,
            arca_doc_tipo=80,
            arca_doc_nro=customer_cuit,
            arca_point_of_sale=ARCA_POINT_OF_SALE,
            arca_request_id=arca_request_id,
            arca_invoice_number=invoice_number,
            arca_cae=f"6110000{invoice_id:06d}",
            arca_cae_expires_at=date.today() + timedelta(days=10),
            arca_result="A",
            arca_observations=[],
        )
        return

    request_status = "rejected" if fiscal_status == "rejected" else "error"
    repository.update_arca_request(
        arca_request_id,
        status=request_status,
        sanitized_response={**response_payload, "error": error_message or fiscal_status},
        error_code="SEED_DEMO",
        error_message=error_message or fiscal_status,
    )
    repository.update_invoice_arca_status(
        invoice_id,
        fiscal_status=fiscal_status,
        arca_environment=ARCA_ENVIRONMENT,
        arca_cuit_emisor=EMITTER_CUIT,
        arca_cbte_tipo=cbte_tipo,
        arca_concepto=1,
        arca_doc_tipo=80,
        arca_doc_nro=customer_cuit,
        arca_point_of_sale=ARCA_POINT_OF_SALE,
        arca_request_id=arca_request_id,
        arca_result="R" if fiscal_status == "rejected" else None,
        arca_observations=[{"code": "SEED", "message": error_message}] if fiscal_status == "rejected" else None,
        arca_error_code="SEED_DEMO",
        arca_error_message=error_message or fiscal_status,
    )


def assert_repo_is_safe_for_demo(repository: PostgresRepository, allow_existing: bool) -> None:
    has_customers = bool(repository.get_profiles_map())
    has_price_lists = bool(repository.list_price_lists())
    has_invoices = bool(repository.list_invoices(limit=1))
    if allow_existing or not (has_customers or has_price_lists or has_invoices):
        return
    raise RuntimeError(
        "La base ya tiene datos operativos. Usa una base vacia para demo o corre con --allow-existing si queres agregar datos igualmente."
    )


def seed_demo_data(*, allow_existing: bool = False) -> None:
    repository = PostgresRepository(Path(__file__).resolve().parents[1])
    assert_repo_is_safe_for_demo(repository, allow_existing)

    transports = [
        repository.save_transport("Transporte Ruta Sur", ["Reparto AMBA", "Entrega lunes a viernes"]),
        repository.save_transport("Logistica Pampeana", ["Cobertura interior", "Paletizado disponible"]),
        repository.save_transport("Expreso del Grano", ["Retiro por deposito", "Ventanas fijas por la tarde"]),
    ]

    internal_price_list = repository.save_price_list_with_catalog(
        filename="lista-mayorista-invierno-2026.pdf",
        pdf_bytes=minimal_pdf_bytes("Lista Mayorista Invierno 2026"),
        catalog=base_catalog_template(),
        activate=True,
        source="demo_seed",
        name="Lista Mayorista Invierno 2026",
    )
    internal_catalog = repository.get_catalog_for_price_list(int(internal_price_list["id"]))

    fiscal_price_list = repository.save_price_list_with_catalog(
        filename="lista-declarada-invierno-2026.pdf",
        pdf_bytes=minimal_pdf_bytes("Lista Declarada Invierno 2026"),
        catalog=fiscal_catalog_from_internal(internal_catalog),
        activate=False,
        source="demo_seed",
        name="Lista Declarada Invierno 2026",
    )
    fiscal_catalog = repository.get_catalog_for_price_list(int(fiscal_price_list["id"]))

    garbanzo_product, garbanzo_offering = catalog_item(internal_catalog, "Garbanzo Kabuli", "x 1 kg")

    profiles = [
        make_profile(
            "Molino del Centro",
            cuit="30711222334",
            address="Av. de los Acopios 1450, Cordoba",
            business_name="Molino del Centro SRL",
            email="compras@molinodelcentro.demo",
            transport=transports[0]["name"],
            secondary_line="Descarga 7 a 15 hs",
            notes=["Cliente mayorista", "Controlar lotes de avena"],
            footer_discounts=[{"label": "Pronto pago", "rate": 0.04}],
        ),
        make_profile(
            "Legumbres del Valle",
            cuit="30722333445",
            address="Ruta 9 km 612, Villa Maria",
            business_name="Legumbres del Valle SAS",
            email="administracion@legumbresdelvalle.demo",
            transport=transports[1]["name"],
            secondary_line="Recibe mercaderia con turno previo",
            notes=["Facturacion semanal", "Enviar remito por mail"],
            line_discounts_by_format={"Bolsa 25 kg": 0.03},
        ),
        make_profile(
            "Distribuidora Don Mateo",
            cuit="30733444556",
            address="Parque Industrial Norte 220, Rosario",
            business_name="Distribuidora Don Mateo SA",
            email="pedidos@donmateo.demo",
            transport=transports[0]["name"],
            notes=["Solicita mercaderia paletizada"],
        ),
        make_profile(
            "Almacen Naturista Horizonte",
            cuit="30744555667",
            address="Belgrano 842, San Miguel de Tucuman",
            business_name="Horizonte Natural SAS",
            email="compras@horizontenatural.demo",
            transport=transports[2]["name"],
            secondary_line="Deposito fondo", 
            notes=["Venta fraccionada", "Prioriza productos de rotacion rapida"],
            automatic_bonus_rules=[
                {
                    "product_id": int(garbanzo_product["id"]),
                    "offering_id": int(garbanzo_offering["id"]),
                    "buy_quantity": 10,
                    "bonus_quantity": 1,
                }
            ],
        ),
        make_profile(
            "Cooperativa La Trilla",
            cuit="30755666778",
            address="Ruta Provincial 4 s/n, Rafaela",
            business_name="Cooperativa La Trilla Ltda.",
            email="logistica@latrilla.demo",
            transport=transports[1]["name"],
            secondary_line="Ingreso por porton 2",
            notes=["Compra mixta cereales y legumbres"],
            footer_discounts=[{"label": "Volumen mensual", "rate": 0.02}],
        ),
    ]
    saved_profiles = [repository.save_profile(profile) for profile in profiles]
    profiles_by_name = {str(profile["name"]): profile for profile in saved_profiles}

    today = date.today()
    created_invoice_ids: list[int] = []

    internal_invoice_id = create_internal_invoice(
        repository,
        profiles_by_name["Molino del Centro"],
        make_order(
            profiles_by_name["Molino del Centro"],
            when=today - timedelta(days=1),
            price_list_id=int(internal_price_list["id"]),
            items=[
                order_item(internal_catalog, "Avena Arrollada", "Bolsa 25 kg", quantity=18),
                order_item(internal_catalog, "Garbanzo Kabuli", "x 1 kg", quantity=12, bonus_quantity=1),
            ],
            notes=["Reposicion semanal", "Controlar humedad al cargar"],
        ),
        internal_catalog,
    )
    created_invoice_ids.append(internal_invoice_id)

    internal_fractional_invoice_id = create_internal_invoice(
        repository,
        profiles_by_name["Almacen Naturista Horizonte"],
        make_order(
            profiles_by_name["Almacen Naturista Horizonte"],
            when=today,
            price_list_id=int(internal_price_list["id"]),
            items=[
                order_item(internal_catalog, "Lenteja Turca", "x 1 kg", quantity=14.5),
                order_item(internal_catalog, "Harina de Maiz Precocida", "x 1 kg", quantity=8),
            ],
            notes=["Pedido fraccionado para salon", "Preparar bultos chicos"],
        ),
        internal_catalog,
    )
    created_invoice_ids.append(internal_fractional_invoice_id)

    fiscal_authorized_id = create_fiscal_invoice(
        repository,
        {**profiles_by_name["Legumbres del Valle"], "iva_condition": "IVA Responsable Inscripto"},
        make_order(
            profiles_by_name["Legumbres del Valle"],
            when=today - timedelta(days=2),
            price_list_id=int(fiscal_price_list["id"]),
            items=[
                order_item(fiscal_catalog, "Poroto Alubia", "Bolsa 25 kg", quantity=22),
                order_item(fiscal_catalog, "Garbanzo Kabuli", "Bolsa 10 kg", quantity=10),
            ],
            notes=["Carga para sucursal Cordoba", "Facturar con datos fiscales completos"],
            billing_mode="fiscal_only",
            declared=True,
        ),
        fiscal_catalog,
    )
    simulate_arca_status(repository, fiscal_authorized_id, fiscal_status="authorized", customer_cuit="30722333445", invoice_number=1001)
    created_invoice_ids.append(fiscal_authorized_id)

    fiscal_rejected_id = create_fiscal_invoice(
        repository,
        {**profiles_by_name["Distribuidora Don Mateo"], "iva_condition": "IVA Responsable Inscripto"},
        make_order(
            profiles_by_name["Distribuidora Don Mateo"],
            when=today - timedelta(days=3),
            price_list_id=int(fiscal_price_list["id"]),
            items=[
                order_item(fiscal_catalog, "Trigo Burgol Grueso", "Bolsa 25 kg", quantity=9),
                order_item(fiscal_catalog, "Maiz Pisingallo", "x 5 kg", quantity=14),
            ],
            notes=["Cliente solicita comprobante A", "Validar percepciones antes de reenviar"],
            billing_mode="fiscal_only",
            declared=True,
        ),
        fiscal_catalog,
    )
    simulate_arca_status(
        repository,
        fiscal_rejected_id,
        fiscal_status="rejected",
        customer_cuit="30733444556",
        error_message="ARCA rechazo el comprobante por inconsistencia de domicilio fiscal informado.",
    )
    created_invoice_ids.append(fiscal_rejected_id)

    fiscal_error_id = create_fiscal_invoice(
        repository,
        {**profiles_by_name["Cooperativa La Trilla"], "iva_condition": "IVA Responsable Inscripto"},
        make_order(
            profiles_by_name["Cooperativa La Trilla"],
            when=today - timedelta(days=4),
            price_list_id=int(fiscal_price_list["id"]),
            items=[
                order_item(fiscal_catalog, "Arroz Integral Largo Fino", "Bolsa 25 kg", quantity=12),
                order_item(fiscal_catalog, "Avena Arrollada", "Bolsa 10 kg", quantity=16),
            ],
            notes=["Factura pendiente de reintento", "Se corto la autorizacion externa"],
            billing_mode="fiscal_only",
            declared=True,
        ),
        fiscal_catalog,
    )
    simulate_arca_status(
        repository,
        fiscal_error_id,
        fiscal_status="error",
        customer_cuit="30755666778",
        error_message="ARCA no respondio dentro del tiempo esperado.",
    )
    created_invoice_ids.append(fiscal_error_id)

    fiscal_draft_id = create_fiscal_invoice(
        repository,
        {**profiles_by_name["Molino del Centro"], "iva_condition": "IVA Responsable Inscripto"},
        make_order(
            profiles_by_name["Molino del Centro"],
            when=today,
            price_list_id=int(fiscal_price_list["id"]),
            items=[
                order_item(fiscal_catalog, "Harina de Maiz Precocida", "Bolsa 20 kg", quantity=11),
                order_item(fiscal_catalog, "Trigo Burgol Grueso", "x 5 kg", quantity=7),
            ],
            notes=["Pendiente de autorizar en ARCA", "Revisar condicion de entrega"],
            billing_mode="fiscal_only",
            declared=True,
        ),
        fiscal_catalog,
    )
    created_invoice_ids.append(fiscal_draft_id)

    split_profile = {**profiles_by_name["Cooperativa La Trilla"], "iva_condition": "IVA Responsable Inscripto"}
    split_order = make_order(
        split_profile,
        when=today - timedelta(days=1),
        price_list_id=int(internal_price_list["id"]),
        items=[
            order_item(internal_catalog, "Maiz Pisingallo", "Bolsa 25 kg", quantity=13),
            order_item(internal_catalog, "Garbanzo Kabuli", "Bolsa 10 kg", quantity=9),
        ],
        notes=["Operacion dividida 60 fiscal / 40 interna", "Cliente retira por deposito"],
        billing_mode="split",
        declared_percentage=60,
        fiscal_price_list_id=int(fiscal_price_list["id"]),
    )
    internal_split_order, fiscal_split_order = build_split_orders(split_order, internal_catalog, fiscal_catalog)
    internal_split_snapshot = generate_invoice_document(internal_split_order, split_profile, internal_catalog)
    fiscal_split_snapshot = fiscalize_snapshot(generate_invoice_document(fiscal_split_order, split_profile, fiscal_catalog), fiscal_catalog)
    _batch_id, batch_invoice_ids = repository.save_invoice_batch(
        batch={
            "client_name": split_order["client_name"],
            "order_date": split_order["date"],
            "billing_mode": "split",
            "declared_percentage": 60,
            "internal_percentage": 40,
            "internal_price_list_id": int(internal_price_list["id"]),
            "fiscal_price_list_id": int(fiscal_price_list["id"]),
            "transport": split_order["transport"],
            "secondary_line": split_order["secondary_line"],
            "notes": split_order["notes"],
            "profile": split_profile,
        },
        invoices=[
            {
                "order": internal_split_order,
                "snapshot": internal_split_snapshot,
                "split_kind": "internal",
                "split_percentage": 40,
                "fiscal_status": "internal",
            },
            {
                "order": fiscal_split_order,
                "profile": split_profile,
                "snapshot": fiscal_split_snapshot,
                "split_kind": "fiscal",
                "split_percentage": 60,
                "fiscal_status": "draft",
            },
        ],
        update_customer=True,
    )
    created_invoice_ids.extend(batch_invoice_ids)

    internal_credit_note_order = {
        "client_name": "Molino del Centro",
        "date": today.isoformat(),
        "price_list_id": int(internal_price_list["id"]),
        "billing_mode": "internal_credit_note",
        "declared": False,
        "secondary_line": str(profiles_by_name["Molino del Centro"].get("secondary_line") or ""),
        "transport": str(profiles_by_name["Molino del Centro"].get("transport") or ""),
        "notes": ["Devolucion parcial por bolsas humedas"],
        "items": [order_item(internal_catalog, "Avena Arrollada", "Bolsa 25 kg", quantity=2)],
    }
    internal_credit_note_snapshot = generate_invoice_document(
        internal_credit_note_order,
        profiles_by_name["Molino del Centro"],
        internal_catalog,
    )
    internal_credit_note_id = repository.save_invoice(
        internal_credit_note_order,
        profiles_by_name["Molino del Centro"],
        internal_credit_note_snapshot,
        update_customer=False,
        split_kind="internal",
        fiscal_status="internal",
        document_type="NOTA_CREDITO",
        related_invoice_id=internal_invoice_id,
        credit_reason="Devolucion parcial por bolsas humedas",
    )
    created_invoice_ids.append(internal_credit_note_id)

    summary = {
        "transports": len(repository.get_transports()),
        "customers": len(repository.get_profiles_map()),
        "price_lists": len(repository.list_price_lists()),
        "invoices_created": len(created_invoice_ids),
        "invoice_ids": created_invoice_ids,
    }
    print(json.dumps(summary, ensure_ascii=True, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Carga datos demo falsos para Granalia.")
    parser.add_argument(
        "--allow-existing",
        action="store_true",
        help="Permite sembrar datos aunque la base ya tenga datos operativos.",
    )
    args = parser.parse_args()
    seed_demo_data(allow_existing=args.allow_existing)


if __name__ == "__main__":
    main()

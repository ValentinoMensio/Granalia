from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


MONEY_RE = re.compile(r"\$?\s*([0-9]{1,3}(?:\.[0-9]{3})*,[0-9]{2}|[0-9]+,[0-9]{2}|[0-9]+(?:\.[0-9]{2})?)")
DATE_RE = re.compile(r"(\d{2})[/-](\d{2})[/-](\d{4})")
CREDIT_NOTE_RE = re.compile(r"NOTA\s+(?:DE\s+)?CR[EÉ]DITO|N\.?\s*CREDITO|NOTA.{0,80}?CR[EÉ]DITO", re.IGNORECASE | re.DOTALL)


@dataclass
class HistoricalInvoiceItem:
    label: str
    quantity: Decimal
    unit: str
    unit_price: Decimal
    discount_rate: Decimal
    subtotal: Decimal
    iva_rate: Decimal | None
    fiscal_total: Decimal


@dataclass
class HistoricalInvoice:
    source_pdf: Path
    document_type: str
    cbte_tipo: int
    point_of_sale: int
    invoice_number: int
    issue_date: date
    customer_name: str
    customer_cuit: str
    customer_address: str
    customer_iva_condition: str
    cae: str | None
    cae_expires_at: date | None
    net_by_rate: dict[Decimal, Decimal]
    iva_by_rate: dict[Decimal, Decimal]
    total: Decimal
    items: list[HistoricalInvoiceItem]


def compact_text(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text.replace("\xa0", " ")).strip()


def normalize_lookup_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text).lower()
    return re.sub(r"\s+", " ", text).strip()


def extract_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ModuleNotFoundError as error:
        raise RuntimeError("Falta instalar pypdf. En el backend está declarado en requirements.txt.") from error
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def parse_date(value: str) -> date | None:
    match = DATE_RE.search(value)
    if not match:
        return None
    day, month, year = match.groups()
    return date(int(year), int(month), int(day))


def first_date(text: str) -> date | None:
    for match in DATE_RE.finditer(text):
        parsed = parse_date(match.group(0))
        if parsed and 2000 <= parsed.year <= 2100:
            return parsed
    return None


def invoice_number_from_filename(path: Path) -> int | None:
    match = re.match(r"(\d+)", path.stem)
    return int(match.group(1)) if match else None


def is_credit_note_filename(path: Path) -> bool:
    return bool(re.match(r"\d+n\b", path.stem.lower()))


def is_credit_note_text(text: str) -> bool:
    return bool(CREDIT_NOTE_RE.search(text))


def should_process_credit_note(path: Path) -> tuple[bool, str]:
    raw_text = extract_text(path)
    text = compact_text(raw_text)
    return is_credit_note_filename(path) or is_credit_note_text(text), raw_text


def parse_money(value: str | None) -> Decimal | None:
    if not value:
        return None
    match = MONEY_RE.search(value)
    if not match:
        return None
    raw = match.group(1)
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    return Decimal(raw).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def find_first(patterns: list[str], text: str, flags: int = re.IGNORECASE) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return next((group for group in match.groups() if group is not None), match.group(0)).strip()
    return None


def clean_label_value(value: str) -> str:
    text = re.sub(r"\s+", " ", value or "").strip(" :-")
    text = re.split(
        r"\b(?:CUIT|Domicilio\s+Comercial|Condici[oó]n\s+frente\s+al\s+IVA|Condici[oó]n\s+de\s+venta|Apellido\s+y\s+Nombre|Raz[oó]n\s+Social|Fecha)\b\s*: ?",
        text,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip(" :-")
    return text[:255]


def first_header_lines(text: str) -> list[str]:
    first_copy = first_invoice_copy_text(text)
    return [line.strip() for line in first_copy.splitlines() if line.strip()]


def parse_customer_header(text: str) -> dict[str, str]:
    lines = first_header_lines(text)
    date_index = next((index for index, line in enumerate(lines) if DATE_RE.fullmatch(line)), None)
    if date_index is None:
        return {}
    end_index = next((index for index in range(date_index + 1, len(lines)) if re.search(r"Cuenta\s+Corriente|Contado", lines[index], re.IGNORECASE)), len(lines))
    values = lines[date_index + 1:end_index]
    if values and re.fullmatch(r"\d{11}", values[0].replace("-", "")):
        values = values[1:]
    if not values:
        return {}

    cuit = ""
    name_parts: list[str] = []
    address = ""
    first_value = values[0]
    match = re.match(r"(\d{2}-?\d{8}-?\d|\d{11})\s+(.+)", first_value)
    if match:
        cuit = match.group(1).replace("-", "")
        name_parts.append(match.group(2).strip())
        remaining = values[1:]
    else:
        name_parts.append(first_value)
        remaining = values[1:]

    for line in remaining:
        if not address and re.search(r"\d|\s-\s|,\s*[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", line):
            address = line
            continue
        if not address:
            name_parts.append(line)
        else:
            address = f"{address} {line}".strip()

    if not cuit:
        cuit_matches = re.findall(r"CUIT\s*:?\s*(\d{2}-?\d{8}-?\d|\d{11})", first_copy_text(text), re.IGNORECASE)
        issuer_cuit = values[0].replace("-", "") if values else ""
        cuit = next((item.replace("-", "") for item in cuit_matches if item.replace("-", "") != issuer_cuit), "")

    return {
        "name": clean_label_value(" ".join(name_parts)),
        "cuit": cuit[:32],
        "address": clean_label_value(address)[:500],
    }


def first_copy_text(text: str) -> str:
    return first_invoice_copy_text(text)


def is_bad_customer_candidate(value: str) -> bool:
    text = clean_label_value(value).upper()
    if not text:
        return True
    bad_fragments = ["DOMICILIO COMERCIAL", "CONDICION", "CONDICIÓN", "CUIT", "FECHA", "MENSIO", "GRANALIA"]
    return any(fragment in text for fragment in bad_fragments)


def parse_label_from_lines(text: str, label_pattern: str, *, max_length: int = 255) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        match = re.search(label_pattern, line, re.IGNORECASE)
        if not match:
            continue
        candidate = clean_label_value(line[match.end():])
        if candidate:
            return candidate[:max_length]
        for next_line in lines[index + 1:index + 4]:
            candidate = clean_label_value(next_line)
            if candidate:
                return candidate[:max_length]
    return ""


def parse_amount_after_label(text: str, labels: list[str]) -> Decimal | None:
    for label in labels:
        pattern = rf"{label}\s*:?\s*\$?\s*([0-9.]+,[0-9]{{2}}|[0-9]+(?:\.[0-9]{{2}})?)"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return parse_money(match.group(1))
    return None


def parse_decimal(value: str) -> Decimal:
    return Decimal(value.replace(".", "").replace(",", "."))


def parse_iva_rate(value: str) -> Decimal:
    return (parse_decimal(value) / Decimal("100")).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def first_invoice_copy_text(raw_text: str) -> str:
    match = re.search(r"(?=Fecha\s+de\s+Emisi[oó]n:\s*\nORIGINAL\b)(.*?)(?=\nFecha\s+de\s+Emisi[oó]n:\s*\nDUPLICADO\b|\Z)", raw_text, re.IGNORECASE | re.DOTALL)
    return match.group(1) if match else raw_text


def parse_invoice_items(raw_text: str) -> list[HistoricalInvoiceItem]:
    first_copy = first_invoice_copy_text(raw_text)
    match = re.search(r"IVA\s+Subtotal\s+c/IVA\s*(.*?)(?:\n\s*CAE\s+N|\n\s*Fecha\s+de\s+Vto\.\s+de\s+CAE)", first_copy, re.IGNORECASE | re.DOTALL)
    if match:
        return parse_taxed_invoice_items(match.group(1))

    match = re.search(r"Imp\.\s+Bonif\.\s+Subtotal\s*(.*?)(?:\n\s*Subtotal\s*:\s*\$|\n\s*CAE\s+N)", first_copy, re.IGNORECASE | re.DOTALL)
    if match:
        return parse_untaxed_invoice_items(match.group(1))
    return []


def parse_taxed_invoice_items(detail_text: str) -> list[HistoricalInvoiceItem]:
    item_pattern = re.compile(
        r"^\s*(?P<label>.+?)\s+"
        r"(?P<quantity>\d+(?:\.\d{3})*,\d{2})\s+"
        r"(?P<unit>[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+(?:\s+[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+)*)\s+"
        r"(?P<unit_price>\d+(?:\.\d{3})*,\d{2})\s+"
        r"(?P<discount>\d+(?:\.\d{3})*,\d{2})\s+"
        r"(?P<subtotal>\d+(?:\.\d{3})*,\d{2})\s+"
        r"(?P<iva>\d+(?:[,.]\d+)?)%\s+"
        r"(?P<fiscal_total>\d+(?:\.\d{3})*,\d{2})\s*$",
        re.IGNORECASE,
    )
    items: list[HistoricalInvoiceItem] = []
    pending_label_parts: list[str] = []
    for raw_line in detail_text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        candidate = " ".join([*pending_label_parts, line]).strip()
        item_match = item_pattern.match(candidate)
        if not item_match:
            pending_label_parts.append(line)
            continue
        label = item_match.group("label").strip()
        pending_label_parts = []
        items.append(HistoricalInvoiceItem(
            label=label[:255],
            quantity=parse_decimal(item_match.group("quantity")),
            unit=item_match.group("unit")[:120],
            unit_price=parse_decimal(item_match.group("unit_price")),
            discount_rate=parse_decimal(item_match.group("discount")) / Decimal("100"),
            subtotal=parse_decimal(item_match.group("subtotal")),
            iva_rate=parse_iva_rate(item_match.group("iva")),
            fiscal_total=parse_decimal(item_match.group("fiscal_total")),
        ))
    return items


def parse_untaxed_invoice_items(detail_text: str) -> list[HistoricalInvoiceItem]:
    item_pattern = re.compile(
        r"^\s*(?P<label>.+?)\s+"
        r"(?P<quantity>\d+(?:\.\d{3})*,\d{2})\s+"
        r"(?P<unit>[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+(?:\s+[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+)*)\s+"
        r"(?P<unit_price>\d+(?:\.\d{3})*,\d{2})\s+"
        r"(?P<rest>.+?)\s*$",
        re.IGNORECASE,
    )
    items: list[HistoricalInvoiceItem] = []
    pending_label_parts: list[str] = []
    for raw_line in detail_text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        candidate = " ".join([*pending_label_parts, line]).strip()
        item_match = item_pattern.match(candidate)
        if not item_match:
            pending_label_parts.append(line)
            continue
        quantity = parse_decimal(item_match.group("quantity"))
        unit_price = parse_decimal(item_match.group("unit_price"))
        gross = (quantity * unit_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        amounts = [parse_decimal(value) for value in MONEY_RE.findall(item_match.group("rest"))]
        subtotal = next((amount for amount in amounts if amount == gross), gross)
        items.append(HistoricalInvoiceItem(
            label=item_match.group("label").strip()[:255],
            quantity=quantity,
            unit=item_match.group("unit")[:120],
            unit_price=unit_price,
            discount_rate=Decimal("0"),
            subtotal=subtotal,
            iva_rate=None,
            fiscal_total=subtotal,
        ))
        pending_label_parts = []
    return items


def parse_number_pair(text: str) -> tuple[int, int] | None:
    patterns = [
        r"Punto\s+de\s+Venta\s*:?\s*(\d{1,5}).{0,80}?Comp\.?\s*Nro\s*:?\s*(\d+)",
        r"Punto\s+de\s+Venta\s*:?\s*(\d{1,5}).{0,120}?Comp\.?\s*(?:Nro|N[°º])\s*:?\s*(\d+)",
        r"Pto\.?\s*Vta\.?\s*:?\s*(\d{1,5}).{0,80}?Nro\.?\s*:?\s*(\d+)",
        r"Pto\.?\s*Vta\.?\s*:?\s*(\d{1,5}).{0,120}?Comp\.?\s*(?:Nro|N[°º])\s*:?\s*(\d+)",
        r"(\d{4,5})\s*[-–—]\s*(\d{1,8})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            return int(match.group(1)), int(match.group(2))
    return None


def parse_customer_name(text: str) -> str:
    header_name = parse_customer_header(text).get("name", "")
    if not is_bad_customer_candidate(header_name):
        return header_name[:255]
    from_lines = parse_label_from_lines(text, r"Apellido\s+y\s+Nombre\s*/\s*Raz[oó]n\s+Social\s*:?|Raz[oó]n\s+Social\s*:?|Cliente\s*:?")
    if not is_bad_customer_candidate(from_lines):
        return from_lines[:255]
    patterns = [
        r"Apellido\s+y\s+Nombre\s*/\s*Raz[oó]n\s+Social\s*:?\s*([^\n]+)",
        r"Raz[oó]n\s+Social\s*:?\s*([^\n]+)",
        r"Cliente\s*:?\s*([^\n]+)",
    ]
    matches: list[str] = []
    for pattern in patterns:
        matches.extend(item.strip() for item in re.findall(pattern, text, re.IGNORECASE) if item.strip())
    for item in matches:
        candidate = clean_label_value(item)
        if not is_bad_customer_candidate(candidate):
            return candidate[:255]
    return "Cliente histórico"


def parse_customer_address(text: str) -> str:
    header_address = parse_customer_header(text).get("address", "")
    if header_address and not DATE_RE.fullmatch(header_address):
        return header_address[:500]
    return parse_label_from_lines(text, r"Domicilio\s+Comercial\s*:?")[:500]


def parse_customer_iva_condition(text: str) -> str:
    return parse_label_from_lines(text, r"Condici[oó]n\s+frente\s+al\s+IVA\s*:?")[:120]


def parse_customer_cuit(text: str) -> str:
    header_cuit = parse_customer_header(text).get("cuit", "")
    if header_cuit:
        return header_cuit[:32]
    cuits = re.findall(r"CUIT\s*:?\s*(\d{2}-?\d{8}-?\d|\d{11})", text, re.IGNORECASE)
    if not cuits:
        return ""
    # El primer CUIT suele ser el emisor; el último suele ser el receptor.
    return cuits[-1].replace("-", "")[:32]


def parse_pdf(path: Path, forced_point_of_sale: int | None = None, raw_text: str | None = None) -> HistoricalInvoice:
    raw_text = raw_text if raw_text is not None else extract_text(path)
    text = compact_text(raw_text)
    upper = text.upper()
    is_credit_note = is_credit_note_filename(path) or is_credit_note_text(text) or ("NOTA" in upper and "CR" in upper)
    is_invoice_b = bool(re.search(r"FACTURA\s*B|FACTURABCOD\.?\s*006|COD\.?\s*006", text, re.IGNORECASE))
    document_type = "NOTA_CREDITO" if is_credit_note else "FACTURA"
    cbte_tipo = 8 if is_credit_note and is_invoice_b else 3 if is_credit_note else 6 if is_invoice_b else 1

    number_pair = parse_number_pair(text)
    if number_pair:
        parsed_point_of_sale, invoice_number = number_pair
    elif forced_point_of_sale and invoice_number_from_filename(path):
        parsed_point_of_sale = forced_point_of_sale
        invoice_number = invoice_number_from_filename(path) or 0
    else:
        raise ValueError("No se pudo leer punto de venta y número de comprobante")
    point_of_sale = forced_point_of_sale or parsed_point_of_sale

    issue_date_text = find_first([
        r"Fecha\s+de\s+Emisi[oó]n\s*:?\s*(\d{2}[/-]\d{2}[/-]\d{4})",
        r"Fecha\s*:?\s*(\d{2}[/-]\d{2}[/-]\d{4})",
    ], text)
    issue_date = parse_date(issue_date_text or "") or first_date(text)
    if issue_date is None:
        raise ValueError("No se pudo leer fecha de emisión")

    cae = find_first([r"CAE\s*(?:N[°ºro.]*)?\s*:?\s*(\d{10,20})"], text)
    cae_exp_text = find_first([
        r"Fecha\s+de\s+Vto\.?\s+de\s+CAE\s*:?\s*(\d{2}[/-]\d{2}[/-]\d{4})",
        r"Vencimiento\s+CAE\s*:?\s*(\d{2}[/-]\d{2}[/-]\d{4})",
    ], text)

    net_by_rate: dict[Decimal, Decimal] = {}
    iva_by_rate: dict[Decimal, Decimal] = {}
    for rate, labels in {
        Decimal("0.210"): [r"IVA\s*21\s*%", r"IVA\s*21,00\s*%"],
        Decimal("0.105"): [r"IVA\s*10[,.]?5\s*%", r"IVA\s*10,50\s*%"],
    }.items():
        iva_amount = parse_amount_after_label(text, labels)
        if iva_amount and iva_amount > 0:
            iva_by_rate[rate] = iva_amount
            net_by_rate[rate] = (iva_amount / rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    total = parse_amount_after_label(text, [r"Importe\s+Total", r"Total\s+con\s+IVA", r"Total"])
    net_total = parse_amount_after_label(text, [r"Importe\s+Neto\s+Gravado", r"Subtotal\s+Neto", r"Neto\s+Gravado"])
    if not iva_by_rate and net_total is not None:
        # Si el PDF no expone el desglose por alícuota, se conserva como 21% por defecto.
        net_by_rate[Decimal("0.210")] = net_total
        iva_by_rate[Decimal("0.210")] = (net_total * Decimal("0.210")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    items = parse_invoice_items(raw_text)
    if total is None and items:
        total = sum((item.fiscal_total for item in items), Decimal("0.00")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if total is None:
        total = sum((net_by_rate[rate] + iva_by_rate[rate] for rate in net_by_rate), Decimal("0.00"))
    if (not net_by_rate and not items) or total <= 0:
        raise ValueError("No se pudo leer importes fiscales")
    if items:
        item_net_by_rate: dict[Decimal, Decimal] = {}
        item_iva_by_rate: dict[Decimal, Decimal] = {}
        for item in items:
            if item.iva_rate is None:
                continue
            item_net_by_rate[item.iva_rate] = item_net_by_rate.get(item.iva_rate, Decimal("0.00")) + item.subtotal
            item_iva_by_rate[item.iva_rate] = item_iva_by_rate.get(item.iva_rate, Decimal("0.00")) + (item.fiscal_total - item.subtotal)
        if item_net_by_rate:
            net_by_rate = {rate: amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) for rate, amount in item_net_by_rate.items()}
            iva_by_rate = {rate: amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) for rate, amount in item_iva_by_rate.items()}

    return HistoricalInvoice(
        source_pdf=path,
        document_type=document_type,
        cbte_tipo=cbte_tipo,
        point_of_sale=point_of_sale,
        invoice_number=invoice_number,
        issue_date=issue_date,
        customer_name=parse_customer_name(text),
        customer_cuit=parse_customer_cuit(text),
        customer_address=parse_customer_address(text),
        customer_iva_condition=parse_customer_iva_condition(text) or "IVA Responsable Inscripto",
        cae=cae,
        cae_expires_at=parse_date(cae_exp_text or ""),
        net_by_rate=net_by_rate,
        iva_by_rate=iva_by_rate,
        total=total,
        items=items,
    )


def money_int(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def arca_iva_id(rate: Decimal) -> int:
    return 4 if rate.quantize(Decimal("0.001")) == Decimal("0.105") else 5


def historical_invoice_id(invoice: HistoricalInvoice) -> int:
    # IDs negativos para no consumir ni mezclar la secuencia positiva de comprobantes reales futuros.
    return -int((invoice.cbte_tipo * 10**12) + (invoice.point_of_sale * 10**8) + invoice.invoice_number)


def normalized_name(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).lower()


def net_total(invoice: HistoricalInvoice) -> Decimal:
    if not invoice.net_by_rate and invoice.items:
        return sum((item.subtotal for item in invoice.items), Decimal("0.00")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return sum(invoice.net_by_rate.values(), Decimal("0.00")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def iva_total(invoice: HistoricalInvoice) -> Decimal:
    return sum(invoice.iva_by_rate.values(), Decimal("0.00")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def item_gross(item: HistoricalInvoiceItem) -> Decimal:
    return (item.quantity * item.unit_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def item_net_weight_kg(label: str) -> Decimal:
    text = label.lower().replace(",", ".")
    match = re.search(r"\b(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)\s*(kg|kgs|kilo|kilos|gr|g)\b", text)
    if match:
        units = Decimal(match.group(1))
        amount = Decimal(match.group(2))
        unit = match.group(3)
        if unit in {"gr", "g"}:
            amount = amount / Decimal("1000")
        return (units * amount).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    match = re.search(r"\bx\s*(\d+(?:\.\d+)?)\s*(kg|kgs|kilo|kilos|gr|g)\b", text)
    if match:
        amount = Decimal(match.group(1))
        unit = match.group(2)
        if unit in {"gr", "g"}:
            amount = amount / Decimal("1000")
        return amount.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    return Decimal("0.000")


def is_non_product_item_label(label: str) -> bool:
    text = compact_text(label).upper()
    return bool(
        re.search(r"\bFAC\.?(?:\s*[ABC])?\s*:", text)
        or (re.search(r"\bDTO\b|\bDESCUENTO\b", text) and re.search(r"\bSOBRE\b|\bF\d+\b|\bFACTURA\b|\bFAC\b", text))
    )


def canonical_offering_label(label: str) -> str:
    text = normalize_lookup_text(label)
    patterns = [
        (r"\b16\s*x\s*300\s*(?:gr|g)?\b", "16x300 gr"),
        (r"\b12\s*x\s*300\s*(?:gr|g)?\b", "12x300 gr"),
        (r"\b12\s*x\s*350\s*(?:gr|g)?\b", "12x350 gr"),
        (r"\b12\s*x\s*400\s*(?:gr|g)?\b", "12x400 gr"),
        (r"\b10\s*x\s*500\s*(?:gr|g)?\b", "10x500 gr"),
        (r"\b10\s*x\s*(?:1000\s*(?:gr|g)?|1\s*kg)\b", "10x1 kg"),
        (r"\bx\s*4\s*kg\b|\b4\s*kg\b", "x 4 kg"),
        (r"\bx\s*5\s*kg\b|\b5\s*kg\b", "x 5 kg"),
        (r"\bx\s*25\s*kg\b|\b25\s*kg\b", "x 25 kg"),
        (r"\bx\s*30\s*kg\b|\b30\s*kg\b", "x 30 kg"),
    ]
    for pattern, offering_label in patterns:
        if re.search(pattern, text):
            return offering_label
    return ""


def split_historical_item_label(label: str) -> tuple[str, str]:
    if is_non_product_item_label(label):
        return "", ""

    from app.domain.catalog import DEFAULT_CATALOG

    normalized_label = normalize_lookup_text(label)
    for product in sorted(DEFAULT_CATALOG, key=lambda item: len(str(item["name"])), reverse=True):
        names = [str(product["name"]), *(str(alias) for alias in product.get("aliases", []))]
        for name in names:
            normalized_name = normalize_lookup_text(name)
            if normalized_label == normalized_name or normalized_label.startswith(f"{normalized_name} "):
                return str(product["name"]), canonical_offering_label(label)
    return compact_text(label)[:255], canonical_offering_label(label)


def invoice_gross_total(invoice: HistoricalInvoice) -> int:
    if not invoice.items:
        return money_int(net_total(invoice))
    return sum((money_int(item_gross(item)) for item in invoice.items), 0)


def invoice_discount_total(invoice: HistoricalInvoice) -> int:
    if not invoice.items:
        return 0
    return sum((money_int(item_gross(item) - item.subtotal) for item in invoice.items), 0)


def invoice_total_bultos(invoice: HistoricalInvoice) -> Decimal:
    if not invoice.items:
        return Decimal(len(invoice.net_by_rate))
    return sum((item.quantity for item in invoice.items), Decimal("0.00")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def resolve_customer_id(repo: PostgresRepository, connection, invoice: HistoricalInvoice, now) -> int | None:
    name = invoice.customer_name if not is_bad_customer_candidate(invoice.customer_name) else "Cliente histórico"
    row = None
    if invoice.customer_cuit:
        row = connection.execute(select(repo.customers).where(repo.customers.c.cuit == invoice.customer_cuit).limit(1)).mappings().first()
    if row is None and name != "Cliente histórico":
        rows = connection.execute(select(repo.customers.c.id, repo.customers.c.name)).mappings().all()
        for candidate in rows:
            if normalized_name(str(candidate["name"] or "")) == normalized_name(name):
                row = candidate
                break
    if row is not None:
        customer_id = int(row["id"])
        values = {}
        if invoice.customer_cuit:
            values["cuit"] = invoice.customer_cuit
        if invoice.customer_address:
            values["address"] = invoice.customer_address
        if invoice.customer_iva_condition:
            values["business_name"] = name
        if values:
            values["updated_at"] = now
            connection.execute(update(repo.customers).where(repo.customers.c.id == customer_id).values(**values))
        return customer_id
    if name == "Cliente histórico" and not invoice.customer_cuit:
        return None
    return int(connection.execute(
        insert(repo.customers)
        .values(
            name=name,
            cuit=invoice.customer_cuit,
            address=invoice.customer_address,
            business_name=name,
            email="",
            secondary_line="",
            notes=["Creado por importación histórica ARCA"],
            footer_discounts=[],
            line_discounts_by_format={},
            automatic_bonus_rules=[],
            automatic_bonus_disables_line_discount=False,
            source_count=0,
            transport_id=None,
            created_at=now,
            updated_at=now,
        )
        .returning(repo.customers.c.id)
    ).scalar_one())


def find_invoice_to_update(repo: PostgresRepository, connection, invoice: HistoricalInvoice, environment: str):
    exact = connection.execute(
        select(repo.invoices.c.id, repo.invoices.c.fiscal_status, repo.invoices.c.arca_cae)
        .where(
            repo.invoices.c.arca_environment == environment,
            repo.invoices.c.arca_cbte_tipo == invoice.cbte_tipo,
            repo.invoices.c.arca_point_of_sale == invoice.point_of_sale,
            repo.invoices.c.arca_invoice_number == invoice.invoice_number,
        )
        .limit(1)
    ).mappings().first()
    if exact is not None:
        if str(exact["fiscal_status"] or "") == "authorized" and (not invoice.cae or str(exact["arca_cae"] or "") == str(invoice.cae)):
            return int(exact["id"]), "already-authorized"
        return int(exact["id"]), "arca"

    candidates = connection.execute(
        select(repo.invoices.c.id)
        .where(
            repo.invoices.c.document_type == invoice.document_type,
            repo.invoices.c.order_date == invoice.issue_date,
            repo.invoices.c.declared.is_(True),
            repo.invoices.c.arca_invoice_number.is_(None),
            repo.invoices.c.final_total == money_int(net_total(invoice)),
        )
    ).mappings().all()
    if len(candidates) == 1:
        return int(candidates[0]["id"]), "date-total"
    return None, "new"


def create_arca_request(repo: PostgresRepository, connection, invoice_id: int, invoice: HistoricalInvoice, environment: str, now) -> int:
    payload = {
        "source": "historical_pdf_import",
        "source_pdf": str(invoice.source_pdf),
        "PtoVta": invoice.point_of_sale,
        "CbteTipo": invoice.cbte_tipo,
        "CbteNro": invoice.invoice_number,
    }
    response = {
        "result": "HISTORICO",
        "invoice_number": invoice.invoice_number,
        "cae": invoice.cae,
        "cae_expires_at": invoice.cae_expires_at.isoformat() if invoice.cae_expires_at else None,
    }
    request_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return int(connection.execute(
        insert(repo.arca_requests)
        .values(
            invoice_id=invoice_id,
            operation="HISTORICAL_IMPORT",
            environment=environment,
            request_hash=request_hash,
            sanitized_request=payload,
            sanitized_response=response,
            status="authorized",
            created_at=now,
            updated_at=now,
        )
        .returning(repo.arca_requests.c.id)
    ).scalar_one())


def mark_authorized(repo: PostgresRepository, connection, invoice_id: int, invoice: HistoricalInvoice, environment: str, now) -> None:
    arca_request_id = create_arca_request(repo, connection, invoice_id, invoice, environment, now)
    connection.execute(
        update(repo.invoices)
        .where(repo.invoices.c.id == invoice_id)
        .values(
            point_of_sale=invoice.point_of_sale,
            invoice_number=invoice.invoice_number,
            declared=True,
            split_kind="fiscal",
            fiscal_status="authorized",
            fiscal_locked_at=now,
            fiscal_authorized_at=now,
            arca_environment=environment,
            arca_cuit_emisor=os.getenv("GRANALIA_ARCA_CUIT", ""),
            arca_cbte_tipo=invoice.cbte_tipo,
            arca_concepto=1,
            arca_doc_tipo=80 if invoice.customer_cuit else None,
            arca_doc_nro=invoice.customer_cuit or None,
            arca_point_of_sale=invoice.point_of_sale,
            arca_invoice_number=invoice.invoice_number,
            arca_cae=invoice.cae,
            arca_cae_expires_at=invoice.cae_expires_at,
            arca_result="HISTORICO",
            arca_observations={"source_pdf": str(invoice.source_pdf)},
            arca_error_code=None,
            arca_error_message=None,
            arca_request_id=str(arca_request_id),
        )
    )


def insert_historical_invoice(repo: PostgresRepository, connection, invoice: HistoricalInvoice, environment: str, now) -> int:
    rounded_net_total = money_int(net_total(invoice))
    invoice_id = historical_invoice_id(invoice)
    existing_id = connection.execute(select(repo.invoices.c.id).where(repo.invoices.c.id == invoice_id)).scalar_one_or_none()
    if existing_id is not None:
        raise ValueError(f"Ya existe un comprobante histórico con id {invoice_id}")
    customer_id = resolve_customer_id(repo, connection, invoice, now)
    customer_name = invoice.customer_name if not is_bad_customer_candidate(invoice.customer_name) else "Cliente histórico"
    invoice_id = int(connection.execute(
        insert(repo.invoices)
        .values(
            id=invoice_id,
            customer_id=customer_id,
            transport_id=None,
            price_list_id=None,
            batch_id=None,
            related_invoice_id=None,
            credit_reason="Importación histórica" if invoice.document_type == "NOTA_CREDITO" else "",
            legacy_key=f"historical-arca:{environment}:{invoice.cbte_tipo}:{invoice.point_of_sale}:{invoice.invoice_number}",
            document_type=invoice.document_type,
            point_of_sale=invoice.point_of_sale,
            invoice_number=invoice.invoice_number,
            internal_invoice_number=None,
            client_name=customer_name,
            declared=True,
            split_kind="fiscal",
            split_percentage=None,
            fiscal_status="authorized",
            fiscal_locked_at=now,
            fiscal_authorized_at=now,
            price_list_name="Histórico ARCA",
            price_list_effective_date=None,
            customer_cuit=invoice.customer_cuit,
            customer_address=invoice.customer_address,
            customer_business_name=customer_name,
            customer_iva_condition=invoice.customer_iva_condition,
            customer_email="",
            order_date=invoice.issue_date,
            secondary_line="",
            transport="",
            notes=[f"Importado desde {invoice.source_pdf.name}"],
            footer_discounts=[],
            line_discounts_by_format={},
            total_bultos=invoice_total_bultos(invoice),
            gross_total=invoice_gross_total(invoice),
            discount_total=invoice_discount_total(invoice),
            final_total=rounded_net_total,
            created_at=now,
        )
        .returning(repo.invoices.c.id)
    ).scalar_one())

    if invoice.items:
        for line_number, item in enumerate(invoice.items, start=1):
            gross = item_gross(item)
            discount = gross - item.subtotal
            iva_amount = (item.fiscal_total - item.subtotal).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            product_name, offering_label = split_historical_item_label(item.label)
            net_weight_label = offering_label or item.label
            connection.execute(
                insert(repo.invoice_items)
                .values(
                    invoice_id=invoice_id,
                    line_number=line_number,
                    product_id=None,
                    offering_id=None,
                    product_name=product_name,
                    offering_label=offering_label,
                    offering_net_weight_kg=item_net_weight_kg(net_weight_label),
                    line_type="sale",
                    discount_rate=item.discount_rate,
                    label=item.label,
                    quantity=item.quantity,
                    unit_price=money_int(item.unit_price),
                    gross=money_int(gross),
                    discount=money_int(discount),
                    total=money_int(item.subtotal),
                    iva_rate=item.iva_rate,
                    net_amount=item.subtotal,
                    iva_amount=iva_amount,
                    fiscal_total=item.fiscal_total,
                )
            )
    else:
        for line_number, (rate, net_amount) in enumerate(sorted(invoice.net_by_rate.items()), start=1):
            iva_amount = invoice.iva_by_rate[rate]
            fiscal_total = (net_amount + iva_amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            label = f"Comprobante histórico {invoice.document_type.replace('_', ' ')} A {invoice.point_of_sale:04d}-{invoice.invoice_number:08d} IVA {Decimal(rate * 100).normalize()}%"
            rounded_net = money_int(net_amount)
            connection.execute(
                insert(repo.invoice_items)
                .values(
                    invoice_id=invoice_id,
                    line_number=line_number,
                    product_id=None,
                    offering_id=None,
                    product_name="",
                    offering_label="",
                    offering_net_weight_kg=0,
                    line_type="sale",
                    discount_rate=0,
                    label=label,
                    quantity=1,
                    unit_price=rounded_net,
                    gross=rounded_net,
                    discount=0,
                    total=rounded_net,
                    iva_rate=rate,
                    net_amount=net_amount,
                    iva_amount=iva_amount,
                    fiscal_total=fiscal_total,
                )
            )

    for rate, net_amount in sorted(invoice.net_by_rate.items()):
        iva_amount = invoice.iva_by_rate[rate]
        connection.execute(
            insert(repo.invoice_tax_breakdown)
            .values(
                invoice_id=invoice_id,
                iva_rate=rate,
                arca_iva_id=arca_iva_id(rate),
                base_amount=net_amount,
                iva_amount=iva_amount,
                created_at=now,
            )
        )

    mark_authorized(repo, connection, invoice_id, invoice, environment, now)
    return invoice_id


def import_invoice(repo: PostgresRepository, invoice: HistoricalInvoice, *, environment: str, dry_run: bool) -> tuple[str, str]:
    with repo.engine.begin() as connection:
        invoice_id, match_kind = find_invoice_to_update(repo, connection, invoice, environment)
        if match_kind == "already-authorized":
            return "skipped", match_kind
        if dry_run:
            action = "update" if invoice_id else "insert"
            return action, match_kind
        now = utc_now()
        if invoice_id:
            mark_authorized(repo, connection, invoice_id, invoice, environment, now)
            return "updated", match_kind
        inserted_id = insert_historical_invoice(repo, connection, invoice, environment, now)
        return "inserted", str(inserted_id)


def delete_historical(repo: PostgresRepository, *, dry_run: bool) -> int:
    with repo.engine.begin() as connection:
        ids = connection.execute(
            select(repo.invoices.c.id).where(
                (repo.invoices.c.id < 0) | (repo.invoices.c.legacy_key.like("historical-arca:%"))
            )
        ).scalars().all()
        if not dry_run and ids:
            connection.execute(repo.invoices.delete().where(repo.invoices.c.id.in_(ids)))
        return len(ids)


def iter_pdf_files(pdf_dir: Path) -> list[Path]:
    return sorted(
        (path for path in pdf_dir.iterdir() if path.suffix.lower() == ".pdf"),
        key=lambda path: [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", path.name.lower())],
    )


def print_debug_pdf(path: Path, limit: int) -> None:
    raw_text = extract_text(path)
    text = compact_text(raw_text)
    print(f"Archivo: {path}")
    print(f"Caracteres extraídos: raw={len(raw_text)} compact={len(text)}")
    print("--- RAW ---")
    print(raw_text[:limit])
    print("--- COMPACT ---")
    print(text[:limit])


def main() -> None:
    global PostgresRepository, insert, select, update, utc_now

    parser = argparse.ArgumentParser(description="Importa PDFs fiscales autorizados manualmente en ARCA como histórico.")
    parser.add_argument("--pdf-dir", type=Path, default=BACKEND_DIR.parent / "docs" / "preubas")
    parser.add_argument("--point-of-sale", type=int, default=2, help="Punto de venta ARCA histórico")
    parser.add_argument("--environment", choices=["produccion", "homologacion"], default="produccion")
    parser.add_argument("--only-credit-notes", action="store_true", help="Importa solo notas de crédito")
    parser.add_argument("--delete-historical", action="store_true", help="Borra solo comprobantes históricos importados por este script")
    parser.add_argument("--replace-historical", action="store_true", help="Borra históricos importados y vuelve a cargar desde los PDFs")
    parser.add_argument("--debug-pdf", type=Path, help="Imprime el texto extraído de un PDF y sale")
    parser.add_argument("--debug-limit", type=int, default=6000, help="Cantidad de caracteres a imprimir con --debug-pdf")
    parser.add_argument("--apply", action="store_true", help="Escribe cambios. Sin este flag solo muestra dry-run.")
    args = parser.parse_args()

    if args.debug_pdf:
        print_debug_pdf(args.debug_pdf, args.debug_limit)
        return

    from sqlalchemy import insert, select, update

    from app.infrastructure.postgres import PostgresRepository
    from app.infrastructure.postgres_utils import utc_now

    repo = PostgresRepository(BACKEND_DIR)
    dry_run = not args.apply
    if args.delete_historical or args.replace_historical:
        count = delete_historical(repo, dry_run=dry_run)
        print(f"Históricos {'a borrar' if dry_run else 'borrados'}: {count}")
        if args.delete_historical and not args.replace_historical:
            if dry_run:
                print("Dry-run finalizado. Ejecutá nuevamente con --apply para escribir cambios.")
            return
    failures = 0
    for path in iter_pdf_files(args.pdf_dir):
        raw_text = None
        try:
            if args.only_credit_notes:
                is_credit_note, raw_text = should_process_credit_note(path)
                if not is_credit_note:
                    continue
            invoice = parse_pdf(path, forced_point_of_sale=args.point_of_sale, raw_text=raw_text)
            action, detail = import_invoice(repo, invoice, environment=args.environment, dry_run=dry_run)
            print(
                f"{path.name}: {action} {detail} | {invoice.document_type} "
                f"PV {invoice.point_of_sale} Nro {invoice.invoice_number} "
                f"{invoice.issue_date.isoformat()} {invoice.customer_name} total={invoice.total}"
            )
        except Exception as error:
            failures += 1
            print(f"{path.name}: ERROR {error}")
    if dry_run:
        print("Dry-run finalizado. Ejecutá nuevamente con --apply para escribir cambios.")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

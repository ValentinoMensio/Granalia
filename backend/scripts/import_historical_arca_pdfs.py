from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
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
class HistoricalInvoice:
    source_pdf: Path
    document_type: str
    cbte_tipo: int
    point_of_sale: int
    invoice_number: int
    issue_date: date
    customer_name: str
    customer_cuit: str
    cae: str | None
    cae_expires_at: date | None
    net_by_rate: dict[Decimal, Decimal]
    iva_by_rate: dict[Decimal, Decimal]
    total: Decimal


def compact_text(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text.replace("\xa0", " ")).strip()


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


def parse_amount_after_label(text: str, labels: list[str]) -> Decimal | None:
    for label in labels:
        pattern = rf"{label}\s*:?\s*\$?\s*([0-9.]+,[0-9]{{2}}|[0-9]+(?:\.[0-9]{{2}})?)"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return parse_money(match.group(1))
    return None


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
    patterns = [
        r"Apellido\s+y\s+Nombre\s*/\s*Raz[oó]n\s+Social\s*:?\s*([^\n]+)",
        r"Raz[oó]n\s+Social\s*:?\s*([^\n]+)",
        r"Cliente\s*:?\s*([^\n]+)",
    ]
    matches: list[str] = []
    for pattern in patterns:
        matches.extend(item.strip() for item in re.findall(pattern, text, re.IGNORECASE) if item.strip())
    for item in matches:
        normalized = item.upper()
        if "MENSIO" not in normalized and "GRANALIA" not in normalized:
            return item[:255]
    return (matches[-1] if matches else "Cliente histórico")[:255]


def parse_customer_cuit(text: str) -> str:
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
    document_type = "NOTA_CREDITO" if is_credit_note else "FACTURA"
    cbte_tipo = 3 if is_credit_note else 1

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
    if total is None:
        total = sum((net_by_rate[rate] + iva_by_rate[rate] for rate in net_by_rate), Decimal("0.00"))
    if not net_by_rate or total <= 0:
        raise ValueError("No se pudo leer importes fiscales")

    return HistoricalInvoice(
        source_pdf=path,
        document_type=document_type,
        cbte_tipo=cbte_tipo,
        point_of_sale=point_of_sale,
        invoice_number=invoice_number,
        issue_date=issue_date,
        customer_name=parse_customer_name(text),
        customer_cuit=parse_customer_cuit(text),
        cae=cae,
        cae_expires_at=parse_date(cae_exp_text or ""),
        net_by_rate=net_by_rate,
        iva_by_rate=iva_by_rate,
        total=total,
    )


def money_int(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def arca_iva_id(rate: Decimal) -> int:
    return 4 if rate.quantize(Decimal("0.001")) == Decimal("0.105") else 5


def historical_invoice_id(invoice: HistoricalInvoice) -> int:
    # IDs negativos para no consumir ni mezclar la secuencia positiva de comprobantes reales futuros.
    return -int((invoice.cbte_tipo * 10**12) + (invoice.point_of_sale * 10**8) + invoice.invoice_number)


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
            repo.invoices.c.final_total == money_int(invoice.total),
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
    rounded_total = money_int(invoice.total)
    invoice_id = historical_invoice_id(invoice)
    existing_id = connection.execute(select(repo.invoices.c.id).where(repo.invoices.c.id == invoice_id)).scalar_one_or_none()
    if existing_id is not None:
        raise ValueError(f"Ya existe un comprobante histórico con id {invoice_id}")
    invoice_id = int(connection.execute(
        insert(repo.invoices)
        .values(
            id=invoice_id,
            customer_id=None,
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
            client_name=invoice.customer_name,
            declared=True,
            split_kind="fiscal",
            split_percentage=None,
            fiscal_status="authorized",
            fiscal_locked_at=now,
            fiscal_authorized_at=now,
            price_list_name="Histórico ARCA",
            price_list_effective_date=None,
            customer_cuit=invoice.customer_cuit,
            customer_address="",
            customer_business_name=invoice.customer_name,
            customer_iva_condition="IVA Responsable Inscripto",
            customer_email="",
            order_date=invoice.issue_date,
            secondary_line="",
            transport="",
            notes=[f"Importado desde {invoice.source_pdf.name}"],
            footer_discounts=[],
            line_discounts_by_format={},
            total_bultos=float(len(invoice.net_by_rate)),
            gross_total=rounded_total,
            discount_total=0,
            final_total=rounded_total,
            created_at=now,
        )
        .returning(repo.invoices.c.id)
    ).scalar_one())

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
    parser.add_argument("--point-of-sale", type=int, default=4, help="Punto de venta ARCA histórico")
    parser.add_argument("--environment", choices=["produccion", "homologacion"], default="produccion")
    parser.add_argument("--only-credit-notes", action="store_true", help="Importa solo notas de crédito")
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

from __future__ import annotations

import base64
import json
import os
import re
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

from PIL import Image, ImageChops
from reportlab.graphics import renderPDF
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from ..core.utils import clean_cell_text, format_quantity
from ..dependencies import BASE_DIR


PAGE_SIZE = A4
MARGIN = 57

FONT_REGULAR = "Helvetica"
FONT_BOLD = "Helvetica-Bold"

COLOR_TEXT = (0.02, 0.02, 0.02)
COLOR_MUTED = (0.28, 0.28, 0.28)
COLOR_LINE = (0.25, 0.25, 0.25)
COLOR_HEADER_BG = (0.78, 0.81, 0.86)
COLOR_FISCAL_LIGHT = (0.94, 0.94, 0.94)
TABLE_PAD_X = 0
TABLE_INNER_PAD_X = 8
ITEM_FONT_SIZE = 12
ITEM_ROW_HEIGHT = 20
SUMMARY_FONT_SIZE = 14
ARCA_QR_URL = "https://www.arca.gob.ar/fe/qr/?p="

def _money(value: int | float) -> str:
    return f"$ {int(round(value or 0)):,}".replace(",", ".")


def _fiscal_money(value: object) -> str:
    amount = Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    integer, decimal = f"{amount:.2f}".split(".")
    return f"$ {int(integer):,}".replace(",", ".") + f",{decimal}"


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip() or default


def _decimal(value: object) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _digits(value: object) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _fiscal_percent(value: object) -> str:
    percent = Decimal(str(value or 0)) * Decimal("100")
    return f"{percent.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}".replace(".", ",")


def _fiscal_document_number(value: object) -> str:
    number = int(value or 0)
    return str(number).zfill(8) if number else "-"


def _fiscal_document_number_unpadded(value: object) -> str:
    number = int(value or 0)
    return str(number) if number else "sin-numero"


def invoice_pdf_filename(invoice: dict) -> str:
    """Nombre sugerido para guardar el PDF.

    Para facturas declaradas usa el número de comprobante de ARCA sin ceros
    a la izquierda, por ejemplo: factura-1838.pdf.
    """
    if _is_fiscal_invoice(invoice):
        number = invoice.get("arca_invoice_number") or invoice.get("fiscal_number") or invoice.get("id")
        return f"factura-{_fiscal_document_number_unpadded(number)}.pdf"

    return f"factura-{_digits(invoice.get('id')) or invoice.get('id')}.pdf"


def _is_fiscal_invoice(invoice: dict) -> bool:
    return bool(invoice.get("declared")) or invoice.get("split_kind") == "fiscal"


def _date(value: object) -> str:
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").strftime("%d-%m-%Y")
    except ValueError:
        return str(value or "")


def _discount_summary(invoice: dict) -> str:
    line_discounts = invoice.get("line_discounts_by_format") or {}

    if line_discounts:
        rates = sorted(
            {
                round(float(rate) * 100, 2)
                for rate in line_discounts.values()
                if float(rate) > 0
            }
        )
        return " + ".join(f"{rate:g}%" for rate in rates) or "Sin descuentos"

    footer_discounts = invoice.get("footer_discounts") or []
    rates = [
        round(float(item.get("rate") or 0) * 100, 2)
        for item in footer_discounts
        if float(item.get("rate") or 0) > 0
    ]

    return " + ".join(f"{rate:g}%" for rate in rates) or "Sin descuentos"


def _set_color(pdf: canvas.Canvas, color: tuple[float, float, float]) -> None:
    pdf.setFillColorRGB(*color)
    pdf.setStrokeColorRGB(*color)


def _line(pdf: canvas.Canvas, x1: float, y: float, x2: float) -> None:
    pdf.setStrokeColorRGB(*COLOR_LINE)
    pdf.setLineWidth(1.1)
    pdf.line(x1, y, x2, y)
    _set_color(pdf, COLOR_TEXT)


def _truncate(text: str, font: str, size: float, max_width: float) -> str:
    text = str(text or "").strip()

    if stringWidth(text, font, size) <= max_width:
        return text

    while text and stringWidth(f"{text}...", font, size) > max_width:
        text = text[:-1]

    return f"{text}..."


def _wrap_text(text: str, font: str, size: float, max_width: float) -> list[str]:
    words = str(text or "").split()
    lines: list[str] = []
    current = ""

    for word in words:
        candidate = f"{current} {word}".strip()
        if not current or stringWidth(candidate, font, size) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines or [""]


def _wrap_text_with_first_width(text: str, font: str, size: float, first_width: float, next_width: float) -> list[str]:
    words = str(text or "").split()
    lines: list[str] = []
    current = ""
    max_width = first_width

    for word in words:
        candidate = f"{current} {word}".strip()
        if not current or stringWidth(candidate, font, size) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
            max_width = next_width

    if current:
        lines.append(current)

    return lines or [""]


def _kilograms_per_unit(label: str) -> float:
    text = str(label or "").lower().replace(" ", "")
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


def _item_weight(item: dict) -> float:
    explicit_weight = item.get("offering_net_weight_kg") or item.get("net_weight_kg")
    if explicit_weight:
        return float(item.get("quantity") or 0) * float(explicit_weight)

    label = item.get("offering_label") or item.get("label") or ""
    return float(item.get("quantity") or 0) * _kilograms_per_unit(str(label))


def _weight(value: float) -> str:
    formatted = f"{value:.1f}".rstrip("0").rstrip(".").replace(".", ",")
    return f"{formatted} kg"


def _draw_logo(pdf: canvas.Canvas, *, margin: int, y: float, logo_path: Path) -> float:
    if not logo_path.exists():
        return y

    with Image.open(logo_path) as source:
        image = source.convert("RGBA")

        alpha_bbox = image.getchannel("A").getbbox()
        white = Image.new("RGBA", image.size, (255, 255, 255, 0))
        content_bbox = alpha_bbox or ImageChops.difference(image, white).getbbox()

        if content_bbox:
            image = image.crop(content_bbox)

        image_buffer = BytesIO()
        image.save(image_buffer, format="PNG")
        image_buffer.seek(0)

    logo_width = 175
    logo_height = logo_width * image.height / image.width

    pdf.drawImage(
        ImageReader(image_buffer),
        margin,
        y - logo_height,
        width=logo_width,
        height=logo_height,
        preserveAspectRatio=False,
        mask="auto",
    )

    return y


def _draw_header(pdf: canvas.Canvas, invoice: dict, width: float, y: float) -> float:
    logo_path = BASE_DIR / "img" / "logof-bw.png"

    _draw_logo(pdf, margin=MARGIN, y=y + 18, logo_path=logo_path)

    _set_color(pdf, COLOR_TEXT)
    pdf.setFont(FONT_BOLD, 17)
    fiscal_number = str(invoice.get("fiscal_number") or invoice.get("id") or "")
    remito_number = re.sub(r"factura", "Remito", fiscal_number, flags=re.IGNORECASE)
    if not remito_number.lower().startswith("remito"):
        remito_number = f"Remito #{remito_number}"
    pdf.drawRightString(width - MARGIN, y - 8, remito_number)

    pdf.setFont(FONT_REGULAR, 12)
    _set_color(pdf, COLOR_MUTED)
    pdf.drawRightString(width - MARGIN, y - 25, f"Fecha de Emisión: {_date(invoice.get('order_date') or invoice.get('date'))}")

    _set_color(pdf, COLOR_TEXT)

    return y - 130


def _draw_invoice_info(pdf: canvas.Canvas, invoice: dict, y: float) -> float:
    _set_color(pdf, COLOR_TEXT)

    pdf.setFont(FONT_BOLD, 17)
    pdf.drawString(MARGIN, y, f"Cliente: {invoice['client_name']}")
    y -= 23

    customer_fields = [
        ("CUIT", invoice.get("customer_cuit")),
        ("Dirección", invoice.get("customer_address")),
    ]

    pdf.setFont(FONT_REGULAR, 14)
    for label, value in customer_fields:
        text = str(value or "").strip()
        if not text:
            continue
        pdf.drawString(MARGIN, y, f"{label}: {text}")
        y -= 18

    secondary_line = str(invoice.get("secondary_line") or "").strip()
    if secondary_line:
        y -= 18
        _set_color(pdf, COLOR_MUTED)
        pdf.drawString(MARGIN, y, secondary_line)
        _set_color(pdf, COLOR_TEXT)

    return y - 40


def _draw_items_header(pdf: canvas.Canvas, width: float, y: float) -> float:
    pdf.setFillColorRGB(*COLOR_HEADER_BG)
    pdf.rect(MARGIN - TABLE_PAD_X, y - 12, width - (MARGIN * 2) + (TABLE_PAD_X * 2), 30, stroke=0, fill=1)

    pdf.setFont(FONT_BOLD, 16)
    _set_color(pdf, COLOR_TEXT)

    pdf.drawString(MARGIN + TABLE_INNER_PAD_X, y, "Producto")
    pdf.drawRightString(MARGIN + 260, y, "Cant.")
    pdf.drawRightString(MARGIN + 370, y, "Precio")
    pdf.drawRightString(width - MARGIN - TABLE_INNER_PAD_X, y, "Total")

    y -= 12
    _line(pdf, MARGIN, y, width - MARGIN)

    return y - 18


def _draw_item(pdf: canvas.Canvas, item: dict, width: float, y: float, index: int) -> float:
    font_size = ITEM_FONT_SIZE
    row_height = ITEM_ROW_HEIGHT

    pdf.setFont(FONT_BOLD, font_size)
    _set_color(pdf, COLOR_TEXT)

    label = _truncate(
        str(item.get("label") or ""),
        FONT_BOLD,
        font_size,
        max_width=242,
    )

    pdf.drawString(MARGIN + TABLE_INNER_PAD_X, y, label)
    pdf.drawRightString(MARGIN + 250, y, format_quantity(item.get("quantity") or 0))
    pdf.drawRightString(MARGIN + 370, y, _money(item.get("unit_price") or 0))
    pdf.drawRightString(width - MARGIN - TABLE_INNER_PAD_X, y, _money(item.get("total") or 0))

    pdf.setStrokeColorRGB(0.45, 0.45, 0.45)
    pdf.setLineWidth(0.35)
    pdf.line(MARGIN, y - 6, width - MARGIN, y - 6)
    _set_color(pdf, COLOR_TEXT)

    return y - row_height

def _draw_totals(pdf: canvas.Canvas, invoice: dict, width: float, y: float) -> float:
    shipment_label_x = MARGIN + TABLE_INNER_PAD_X
    shipment_value_x = MARGIN + 105
    totals_label_x = width - 240
    totals_value_x = width - MARGIN - TABLE_INNER_PAD_X
    shipment_font_size = 12
    total_bultos = sum(
        float(item.get("quantity") or 0)
        for item in invoice.get("items", [])
    )
    total_weight = sum(_item_weight(item) for item in invoice.get("items", []))
    transport = str(invoice.get("transport") or "").strip()
    notes = [str(note or "").strip() for note in invoice.get("notes", []) if str(note or "").strip()]

    discount_summary = _discount_summary(invoice)
    has_discount = float(invoice.get("discount_total") or 0) > 0

    y -= 14

    pdf.setFont(FONT_BOLD, SUMMARY_FONT_SIZE)
    _set_color(pdf, COLOR_TEXT)

    pdf.drawString(MARGIN + TABLE_INNER_PAD_X, y, "Bultos")
    pdf.drawRightString(MARGIN + 250, y, format_quantity(total_bultos))

    y -= 16
    _line(pdf, MARGIN, y, width - MARGIN)

    y -= 24
    section_top_y = y

    pdf.setFont(FONT_BOLD, 12)
    _set_color(pdf, COLOR_MUTED)
    pdf.drawString(shipment_label_x, section_top_y, "DATOS DEL ENVÍO")

    shipment_y = section_top_y - 18
    shipment_lines = [("Peso neto:", _weight(total_weight))]
    if transport:
        shipment_lines.append(("Transporte:", transport))
    if notes:
        shipment_lines.append(("Observaciones:", " / ".join(notes)))

    shipment_max_width = totals_label_x - shipment_value_x - 20
    for label, value in shipment_lines:
        pdf.setFont(FONT_BOLD, shipment_font_size)
        _set_color(pdf, COLOR_TEXT)
        pdf.drawString(shipment_label_x, shipment_y, label)

        if label == "Observaciones":
            pdf.setFont(FONT_REGULAR, shipment_font_size)
            _set_color(pdf, COLOR_MUTED)
            value_lines = _wrap_text_with_first_width(
                value,
                FONT_REGULAR,
                shipment_font_size,
                shipment_max_width,
                totals_label_x - shipment_label_x - 20,
            )
            for index, line in enumerate(value_lines):
                x = shipment_value_x if index == 0 else shipment_label_x
                y_offset = 0 if index == 0 else index * 14
                pdf.drawString(x, shipment_y - y_offset, line)
            shipment_y -= max(17, len(value_lines) * 14)
            continue

        pdf.setFont(FONT_REGULAR, shipment_font_size)
        _set_color(pdf, COLOR_MUTED)
        value_lines = _wrap_text(value, FONT_REGULAR, shipment_font_size, shipment_max_width)
        for index, line in enumerate(value_lines):
            pdf.drawString(shipment_value_x, shipment_y - (index * 14), line)
        shipment_y -= max(17, len(value_lines) * 14)

    if has_discount:
        _set_color(pdf, COLOR_TEXT)
        pdf.setFont(FONT_BOLD, SUMMARY_FONT_SIZE)
        pdf.drawString(totals_label_x, section_top_y, "Subtotal")
        pdf.drawRightString(totals_value_x, section_top_y, _money(invoice.get("gross_total") or 0))

        totals_y = section_top_y - 18

        discount_label = (
            f"Dto. ({discount_summary})"
            if discount_summary != "Sin dto."
            else "Dto."
        )

        pdf.setFont(FONT_REGULAR, SUMMARY_FONT_SIZE)
        _set_color(pdf, COLOR_MUTED)
        pdf.drawString(totals_label_x, totals_y, _truncate(clean_cell_text(discount_label), FONT_REGULAR, SUMMARY_FONT_SIZE, 210))
        pdf.drawRightString(totals_value_x, totals_y, _money(invoice.get("discount_total") or 0))

        totals_y -= 28
    else:
        totals_y = section_top_y

    pdf.setFont(FONT_BOLD, SUMMARY_FONT_SIZE)
    _set_color(pdf, COLOR_TEXT)
    pdf.drawString(totals_label_x, totals_y, "Total")
    pdf.drawRightString(totals_value_x, totals_y, _money(invoice.get("final_total") or 0))

    return min(shipment_y, totals_y) - 20

def _new_page(pdf: canvas.Canvas, invoice: dict, width: float, height: float) -> float:
    pdf.showPage()

    y = height - 28
    y = _draw_header(pdf, invoice, width, y)
    y = _draw_items_header(pdf, width, y)

    return y


def _issuer_data(invoice: dict) -> dict[str, str]:
    return {
        "business_name": _env("GRANALIA_ISSUER_BUSINESS_NAME", "GRANALIA"),
        "fantasy_name": _env("GRANALIA_ISSUER_FANTASY_NAME", "Granalia"),
        "address": _env("GRANALIA_ISSUER_ADDRESS", "Celestina Aguero 609 Piso:0 Dpto:0 - Alta Gracia, Córdoba"),
        "iva_condition": _env("GRANALIA_ISSUER_IVA_CONDITION", "IVA Responsable Inscripto"),
        "iibb": _env("GRANALIA_ISSUER_IIBB", "280405086"),
        "activity_start": _env("GRANALIA_ISSUER_ACTIVITY_START", "01/03/2011"),
        "cuit": str(invoice.get("arca_cuit_emisor") or _env("GRANALIA_ARCA_CUIT", "20225790346")),
    }


def _fiscal_item_values(item: dict) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
    quantity = Decimal(str(item.get("quantity") or 0))
    unit_price = _decimal(item.get("unit_price") or 0)
    gross = _decimal(item.get("gross") if item.get("gross") is not None else unit_price * quantity)
    discount = _decimal(item.get("effective_discount") if item.get("effective_discount") is not None else item.get("discount") or 0)
    net = _decimal(item.get("net_amount") if item.get("net_amount") is not None else item.get("effective_total") if item.get("effective_total") is not None else gross - discount)
    iva_rate = Decimal(str(item.get("iva_rate") or 0))
    iva = _decimal(item.get("iva_amount") if item.get("iva_amount") is not None else net * iva_rate)
    total = _decimal(item.get("fiscal_total") if item.get("fiscal_total") is not None else net + iva)
    return gross, discount, net, iva, total


def _fiscal_tax_breakdown(invoice: dict) -> list[dict[str, Decimal]]:
    breakdown: dict[Decimal, dict[str, Decimal]] = {}
    for item in invoice.get("items", []):
        rate = Decimal(str(item.get("iva_rate") or 0))
        if rate <= 0:
            continue
        _, _, net, iva, _ = _fiscal_item_values(item)
        current = breakdown.setdefault(rate, {"base": Decimal("0.00"), "iva": Decimal("0.00")})
        current["base"] += net
        current["iva"] += iva

    return [
        {"rate": rate, "base": values["base"].quantize(Decimal("0.01")), "iva": values["iva"].quantize(Decimal("0.01"))}
        for rate, values in sorted(breakdown.items())
    ]


def _fiscal_total(invoice: dict) -> Decimal:
    total = Decimal("0.00")
    for item in invoice.get("items", []):
        total += _fiscal_item_values(item)[4]
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _draw_qr(pdf: canvas.Canvas, data: str, x: float, y: float, size: float) -> None:
    qr_code = qr.QrCodeWidget(data)
    bounds = qr_code.getBounds()
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    drawing = Drawing(size, size, transform=[size / width, 0, 0, size / height, 0, 0])
    drawing.add(qr_code)
    renderPDF.draw(drawing, pdf, x, y)


def _arca_qr_url(invoice: dict) -> str | None:
    cae = str(invoice.get("arca_cae") or "").strip()
    invoice_number = int(invoice.get("arca_invoice_number") or 0)
    if not cae or not invoice_number:
        return None

    payload = {
        "ver": 1,
        "fecha": str(invoice.get("order_date") or invoice.get("date") or ""),
        "cuit": int(_digits(invoice.get("arca_cuit_emisor") or _env("GRANALIA_ARCA_CUIT", "20225790346")) or 0),
        "ptoVta": int(invoice.get("arca_point_of_sale") or _env("GRANALIA_ARCA_POINT_OF_SALE", "1") or 1),
        "tipoCmp": int(invoice.get("arca_cbte_tipo") or 1),
        "nroCmp": invoice_number,
        "importe": float(_fiscal_total(invoice)),
        "moneda": "PES",
        "ctz": 1,
        "tipoDocRec": int(invoice.get("arca_doc_tipo") or 80),
        "nroDocRec": int(_digits(invoice.get("arca_doc_nro") or invoice.get("customer_cuit")) or 0),
        "tipoCodAut": "E",
        "codAut": int(_digits(cae) or 0),
    }
    encoded = base64.b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")).decode("ascii")
    return f"{ARCA_QR_URL}{quote(encoded, safe='')}"


def _fiscal_date(value: object) -> str:
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return str(value or "")


def _fiscal_percent_display(value: object) -> str:
    percent = Decimal(str(value or 0)) * Decimal("100")
    rounded = percent.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if rounded == rounded.to_integral():
        return f"{int(rounded)}%"
    return f"{rounded:.1f}".replace(".", ",") + "%"


def _fiscal_amount(value: object, *, currency: bool = False) -> str:
    amount = Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    text = f"{amount:.2f}".replace(".", ",")
    return f"$ {text}" if currency else text


def _invoice_unit(item: dict) -> str:
    return str(item.get("unit") or item.get("uom") or item.get("unit_label") or "packs").lower()


def _draw_fiscal_header(pdf: canvas.Canvas, invoice: dict, width: float, height: float, copy_label: str) -> float:
    issuer = _issuer_data(invoice)
    point_of_sale = int(invoice.get("arca_point_of_sale") or _env("GRANALIA_ARCA_POINT_OF_SALE", "1") or 1)
    invoice_number = _fiscal_document_number(invoice.get("arca_invoice_number"))
    left = 15
    right = width - 15
    top = height - 18
    top_band_bottom = top - 28
    header_bottom = top - 156
    mid_x = left + ((right - left) / 2)

    letter_box_w = 46
    letter_box_h = 42
    letter_left = mid_x - (letter_box_w / 2)
    letter_right = mid_x + (letter_box_w / 2)
    letter_top = top_band_bottom + 3
    letter_bottom = letter_top - letter_box_h
    left_inner_right = letter_left - 10
    right_inner_left = letter_right + 18

    pdf.setLineWidth(0.6)
    pdf.rect(left, header_bottom, right - left, top - header_bottom)
    pdf.line(left, top_band_bottom, right, top_band_bottom)
    pdf.line(mid_x, top_band_bottom, mid_x, letter_top)
    pdf.line(mid_x, letter_bottom, mid_x, header_bottom)

    pdf.setFont(FONT_BOLD, 16)
    pdf.drawCentredString(width / 2, top - 20, copy_label)

    pdf.setFillColorRGB(1, 1, 1)
    pdf.rect(letter_left, letter_bottom, letter_box_w, letter_box_h, fill=1, stroke=1)
    _set_color(pdf, COLOR_TEXT)
    pdf.setFont(FONT_BOLD, 24)
    pdf.drawCentredString(mid_x, letter_top - 21, "A")
    pdf.setFont(FONT_BOLD, 7)
    pdf.drawCentredString(mid_x, letter_bottom + 8, "COD. 01")

    pdf.setFont(FONT_BOLD, 11)
    pdf.drawCentredString((left + left_inner_right) / 2, top_band_bottom - 22, issuer["business_name"])

    left_label_x = left + 6
    left_value_x = left + 106
    left_value_width = left_inner_right - left_value_x - 4
    row1_y = top_band_bottom - 60
    row2_y = top_band_bottom - 88
    row3_y = top_band_bottom - 120

    pdf.setFont(FONT_BOLD, 9)
    pdf.drawString(left_label_x, row1_y, "Razón Social:")
    pdf.setFont(FONT_REGULAR, 9)
    pdf.drawString(
        left + 73,
        row1_y,
        _truncate(
            str(invoice.get("issuer_business_name") or _env("GRANALIA_LEGAL_NAME", "MENSIO OSCAR LEANDRO")),
            FONT_REGULAR,
            9,
            left_inner_right - (left + 73) - 4,
        ),
    )

    pdf.setFont(FONT_BOLD, 9)
    pdf.drawString(left_label_x, row2_y, "Domicilio Comercial:")
    pdf.setFont(FONT_REGULAR, 9)
    issuer_address = str(invoice.get("issuer_address") or issuer["address"])
    address_lines = _wrap_text(issuer_address, FONT_REGULAR, 9, left_value_width)[:2]
    for index, line in enumerate(address_lines):
        pdf.drawString(left_value_x, row2_y - (index * 10), line)

    pdf.setFont(FONT_BOLD, 9)
    pdf.drawString(left_label_x, row3_y, "Condición frente al IVA:")
    pdf.drawString(left + 116, row3_y, _truncate(issuer["iva_condition"], FONT_BOLD, 9, left_inner_right - (left + 116) - 4))

    pdf.setFont(FONT_BOLD, 20)
    pdf.drawString(right_inner_left, top_band_bottom - 26, "FACTURA")

    info_y1 = top_band_bottom - 50
    info_y2 = top_band_bottom - 70
    info_y3 = top_band_bottom - 88
    info_y4 = top_band_bottom - 104
    info_y5 = top_band_bottom - 120
    pos_label_x = right_inner_left
    pos_value_x = pos_label_x + 92
    comp_label_x = pos_label_x + 130
    comp_value_right = right - 16

    pdf.setFont(FONT_BOLD, 9)
    pdf.drawString(pos_label_x, info_y1, "Punto de Venta:")
    pdf.drawString(pos_value_x, info_y1, f"{point_of_sale:05d}")
    pdf.drawString(comp_label_x, info_y1, "Comp. Nro:")
    pdf.drawRightString(comp_value_right, info_y1, invoice_number)

    pdf.drawString(pos_label_x, info_y2, "Fecha de Emisión:")
    pdf.drawString(pos_value_x + 3, info_y2, _fiscal_date(invoice.get("order_date") or invoice.get("date")))

    pdf.drawString(pos_label_x, info_y3, "CUIT:")
    pdf.setFont(FONT_REGULAR, 9)
    pdf.drawString(pos_label_x + 35, info_y3, issuer["cuit"])

    pdf.setFont(FONT_BOLD, 9)
    pdf.drawString(pos_label_x, info_y4, "Ingresos Brutos:")
    pdf.setFont(FONT_REGULAR, 9)
    pdf.drawString(pos_label_x + 82, info_y4, issuer["iibb"])

    pdf.setFont(FONT_BOLD, 9)
    pdf.drawString(pos_label_x, info_y5, "Fecha de Inicio de Actividades:")
    pdf.setFont(FONT_REGULAR, 9)
    pdf.drawRightString(right - 16, info_y5, issuer["activity_start"])

    return header_bottom - 8


def _draw_fiscal_receiver(pdf: canvas.Canvas, invoice: dict, width: float, y: float) -> float:
    left = 15
    right = width - 15
    top = y
    height_box = 64
    bottom = top - height_box
    name = invoice.get("customer_business_name") or invoice.get("client_name") or invoice.get("customer_name") or ""
    address = invoice.get("customer_address") or ""
    cuit = invoice.get("arca_doc_nro") or invoice.get("customer_cuit") or ""
    iva_condition = invoice.get("customer_iva_condition") or "IVA Responsable Inscripto"
    sale_condition = invoice.get("payment_condition") or invoice.get("sale_condition") or "Cuenta Corriente"

    pdf.setLineWidth(0.6)
    pdf.rect(left, bottom, right - left, height_box)
    pdf.setFont(FONT_BOLD, 8)
    pdf.drawString(left + 6, top - 13, "CUIT:")
    pdf.setFont(FONT_REGULAR, 8)
    pdf.drawString(left + 39, top - 13, str(cuit))

    pdf.setFont(FONT_BOLD, 8)
    pdf.drawString(left + 214, top - 13, "Apellido y Nombre / Razón Social:")
    pdf.setFont(FONT_REGULAR, 8)
    pdf.drawString(left + 365, top - 13, _truncate(str(name), FONT_REGULAR, 8, 210))

    pdf.setFont(FONT_BOLD, 8)
    pdf.drawString(left + 6, top - 34, "Condición frente al IVA:")
    pdf.setFont(FONT_REGULAR, 8)
    pdf.drawString(left + 112, top - 34, str(iva_condition))

    pdf.setFont(FONT_BOLD, 8)
    pdf.drawString(left + 260, top - 34, "Domicilio Comercial:")
    pdf.setFont(FONT_REGULAR, 8)
    pdf.drawString(left + 361, top - 34, _truncate(str(address), FONT_REGULAR, 8, 215))

    pdf.setFont(FONT_BOLD, 8)
    pdf.drawString(left + 6, top - 54, "Condición de venta:")
    pdf.setFont(FONT_REGULAR, 8)
    pdf.drawString(left + 100, top - 54, str(sale_condition))
    return bottom - 46


def _draw_fiscal_items_header(pdf: canvas.Canvas, width: float, y: float) -> float:
    left = 15
    right = width - 15
    row_h = 19
    pdf.setFillColorRGB(0.78, 0.78, 0.78)
    pdf.rect(left, y - row_h, right - left, row_h, fill=1, stroke=1)
    _set_color(pdf, COLOR_TEXT)
    pdf.setFont(FONT_BOLD, 6.7)
    separators = (left + 40, left + 220, left + 275, left + 317, left + 381, left + 414, left + 480, left + 515)
    for x in separators:
        pdf.line(x, y, x, y - row_h)
    pdf.drawString(left + 5, y - 9, "Código")
    pdf.drawString(left + 43, y - 9, "Producto / Servicio")
    pdf.drawCentredString((left + 220 + left + 275) / 2, y - 9, "Cantidad")
    pdf.drawCentredString((left + 275 + left + 317) / 2, y - 9, "U. medida")
    pdf.drawCentredString((left + 317 + left + 381) / 2, y - 9, "Precio Unit.")
    pdf.drawCentredString((left + 381 + left + 414) / 2, y - 9, "% Bonif")
    pdf.drawCentredString((left + 414 + left + 480) / 2, y - 9, "Subtotal")
    pdf.drawCentredString((left + 480 + left + 515) / 2, y - 8, "Alicuota")
    pdf.drawCentredString((left + 480 + left + 515) / 2, y - 15, "IVA")
    pdf.drawCentredString((left + 515 + right) / 2, y - 9, "Subtotal c/IVA")
    return y - row_h - 16


def _draw_fiscal_item(pdf: canvas.Canvas, item: dict, width: float, y: float, index: int) -> float:
    gross, discount, net, _iva, total = _fiscal_item_values(item)
    discount_rate = (discount / gross) if gross else Decimal("0")
    iva_rate = Decimal(str(item.get("iva_rate") or 0))
    left = 15
    right = width - 15

    pdf.setFont(FONT_REGULAR, 8)
    pdf.drawString(left + 5, y, str(item.get("product_id") or item.get("code") or ""))
    pdf.drawString(left + 43, y, _truncate(str(item.get("label") or ""), FONT_REGULAR, 8, 175))
    pdf.drawRightString(left + 266, y, _fiscal_amount(item.get("quantity") or 0))
    pdf.drawString(left + 286, y, _invoice_unit(item))
    pdf.drawRightString(left + 376, y, _fiscal_amount(item.get("unit_price") or 0))
    pdf.drawRightString(left + 411, y, _fiscal_amount(discount_rate * Decimal("100")))
    pdf.drawRightString(left + 475, y, _fiscal_amount(net))
    pdf.drawRightString(left + 510, y, _fiscal_percent_display(iva_rate))
    pdf.drawRightString(right - 3, y, _fiscal_amount(total))
    return y - 16


def _iva_amount_for_rate(breakdown: list[dict[str, Decimal]], rate: Decimal) -> Decimal:
    for item in breakdown:
        if Decimal(item["rate"]).quantize(Decimal("0.001")) == rate.quantize(Decimal("0.001")):
            return item["iva"]
    return Decimal("0.00")


def _draw_arca_mark(pdf: canvas.Canvas, x: float, y: float) -> None:
    pdf.setFont(FONT_BOLD, 23)
    _set_color(pdf, (0.25, 0.25, 0.25))
    pdf.drawString(x, y, "ARCA")
    pdf.setFont(FONT_REGULAR, 4.5)
    pdf.drawString(x, y - 7, "AGENCIA DE RECAUDACIÓN")
    pdf.drawString(x, y - 12, "Y CONTROL ADUANERO")
    _set_color(pdf, COLOR_TEXT)


def _draw_fiscal_footer(pdf: canvas.Canvas, invoice: dict, width: float, y: float) -> None:
    breakdown = _fiscal_tax_breakdown(invoice)
    net_total = sum((item["base"] for item in breakdown), Decimal("0.00"))
    total = _fiscal_total(invoice)
    iva_27 = _iva_amount_for_rate(breakdown, Decimal("0.27"))
    iva_21 = _iva_amount_for_rate(breakdown, Decimal("0.21"))
    iva_105 = _iva_amount_for_rate(breakdown, Decimal("0.105"))
    iva_5 = _iva_amount_for_rate(breakdown, Decimal("0.05"))
    iva_25 = _iva_amount_for_rate(breakdown, Decimal("0.025"))
    iva_0 = _iva_amount_for_rate(breakdown, Decimal("0"))
    left = 15
    right = width - 15
    top = 330
    bottom = 168

    pdf.setLineWidth(0.6)
    pdf.rect(left, bottom, right - left, top - bottom)

    pdf.setFont(FONT_REGULAR, 9)
    pdf.drawRightString(width / 2 - 15, top - 30, "Importe Otros Tributos: $")
    pdf.drawRightString(width / 2 + 45, top - 30, "0,00")

    label_x = right - 78
    value_x = right - 7
    rows = [
        ("Importe Neto Gravado: $", net_total),
        ("IVA 27%: $", iva_27),
        ("IVA 21%: $", iva_21),
        ("IVA 10.5%: $", iva_105),
        ("IVA 5%: $", iva_5),
        ("IVA 2.5%: $", iva_25),
        ("IVA 0%: $", iva_0),
        ("Importe Otros Tributos: $", Decimal("0.00")),
        ("Importe Total: $", total),
    ]
    row_y = top - 56
    row_step = 12
    for idx, (label, value) in enumerate(rows):
        pdf.setFont(FONT_BOLD, 9 if idx < len(rows) - 1 else 10)
        pdf.drawRightString(label_x, row_y, label)
        pdf.drawRightString(value_x, row_y, _fiscal_amount(value))
        row_y -= row_step

    fantasy = _issuer_data(invoice)["fantasy_name"]
    pdf.rect(left, bottom - 28, right - left, 26)
    pdf.setFont(FONT_REGULAR, 11)
    pdf.drawCentredString(width / 2, bottom - 19, f'"{fantasy.upper()}"')

    qr_url = _arca_qr_url(invoice)
    if qr_url:
        _draw_qr(pdf, qr_url, left + 10, 58, 70)
    else:
        # Mantiene el espacio del QR como en los comprobantes autorizados.
        pdf.rect(left + 10, 58, 70, 70)

    _draw_arca_mark(pdf, left + 105, 111)
    pdf.setFont(FONT_BOLD, 9)
    pdf.drawString(left + 105, 85, "Comprobante Autorizado" if invoice.get("arca_cae") else "Comprobante Pendiente")
    pdf.setFont(FONT_BOLD, 6)
    pdf.drawString(left + 105, 66, "Esta Agencia no se responsabiliza por los datos ingresados en el detalle de la operación")

    pdf.setFont(FONT_BOLD, 9)
    pdf.drawCentredString(width / 2, 112, "Pág. 1/1")
    pdf.drawRightString(right - 102, 107, "CAE N°:")
    pdf.drawString(right - 96, 107, str(invoice.get("arca_cae") or "Pendiente"))
    pdf.drawRightString(right - 102, 88, "Fecha de Vto. de CAE:")
    pdf.drawString(right - 96, 88, _fiscal_date(invoice.get("arca_cae_expires_at")) if invoice.get("arca_cae_expires_at") else "Pendiente")


def _draw_fiscal_copy(pdf: canvas.Canvas, invoice: dict, width: float, height: float, copy_label: str) -> None:
    y = _draw_fiscal_header(pdf, invoice, width, height, copy_label)
    y = _draw_fiscal_receiver(pdf, invoice, width, y)
    y = _draw_fiscal_items_header(pdf, width, y)
    for index, item in enumerate(invoice.get("items", [])):
        if y < 370:
            pdf.showPage()
            y = _draw_fiscal_header(pdf, invoice, width, height, copy_label)
            y = _draw_fiscal_items_header(pdf, width, y)
        y = _draw_fiscal_item(pdf, item, width, y, index)
    _draw_fiscal_footer(pdf, invoice, width, y)


def build_fiscal_invoice_pdf(invoice: dict) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=PAGE_SIZE)
    width, height = PAGE_SIZE
    pdf.setTitle(invoice_pdf_filename(invoice).removesuffix(".pdf"))

    for index, copy_label in enumerate(("ORIGINAL", "DUPLICADO", "TRIPLICADO", "CUADRUPLICADO")):
        if index:
            pdf.showPage()
        _draw_fiscal_copy(pdf, invoice, width, height, copy_label)

    pdf.save()
    return buffer.getvalue()


def build_invoice_pdf(invoice: dict) -> bytes:
    if _is_fiscal_invoice(invoice):
        return build_fiscal_invoice_pdf(invoice)

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=PAGE_SIZE)

    width, height = PAGE_SIZE
    y = height - 28

    pdf.setTitle(f"Remito {invoice['id']}")

    y = _draw_header(pdf, invoice, width, y)
    y = _draw_invoice_info(pdf, invoice, y)
    y = _draw_items_header(pdf, width, y)

    for index, item in enumerate(invoice.get("items", [])):
        if y < 120:
            y = _new_page(pdf, invoice, width, height)

        y = _draw_item(pdf, item, width, y, index)

    y = _draw_totals(pdf, invoice, width, y)

    pdf.save()

    return buffer.getvalue()

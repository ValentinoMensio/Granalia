from __future__ import annotations

import re
from datetime import datetime
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageChops
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
TABLE_PAD_X = 0
TABLE_INNER_PAD_X = 8
ITEM_FONT_SIZE = 12
ITEM_ROW_HEIGHT = 20
SUMMARY_FONT_SIZE = 14

def _money(value: int | float) -> str:
    return f"$ {int(round(value or 0)):,}".replace(",", ".")


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

    _draw_logo(pdf, margin=MARGIN, y=y, logo_path=logo_path)

    _set_color(pdf, COLOR_TEXT)
    pdf.setFont(FONT_BOLD, 17)
    pdf.drawRightString(width - MARGIN, y - 8, f"Factura #{invoice['id']}")

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

    pdf.setFont(FONT_REGULAR, font_size)
    _set_color(pdf, COLOR_TEXT)

    label = _truncate(
        str(item.get("label") or ""),
        FONT_REGULAR,
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


def build_invoice_pdf(invoice: dict) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=PAGE_SIZE)

    width, height = PAGE_SIZE
    y = height - 28

    pdf.setTitle(f"Factura {invoice['id']}")

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

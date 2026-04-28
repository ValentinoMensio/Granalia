from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageChops
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from ..core.utils import clean_cell_text
from ..dependencies import BASE_DIR


PAGE_SIZE = A4
MARGIN = 36

FONT_REGULAR = "Helvetica"
FONT_BOLD = "Helvetica-Bold"

COLOR_TEXT = (0.05, 0.05, 0.05)
COLOR_MUTED = (0.42, 0.42, 0.42)
COLOR_LINE = (0.78, 0.78, 0.78)


def _money(value: int | float) -> str:
    return f"$ {int(round(value or 0)):,}".replace(",", ".")


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
    pdf.setLineWidth(0.6)
    pdf.line(x1, y, x2, y)
    _set_color(pdf, COLOR_TEXT)


def _truncate(text: str, font: str, size: float, max_width: float) -> str:
    text = str(text or "").strip()

    if stringWidth(text, font, size) <= max_width:
        return text

    while text and stringWidth(f"{text}...", font, size) > max_width:
        text = text[:-1]

    return f"{text}..."


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
    logo_path = BASE_DIR / "img" / "logo-bw.png"

    _draw_logo(pdf, margin=MARGIN, y=y, logo_path=logo_path)

    _set_color(pdf, COLOR_TEXT)
    pdf.setFont(FONT_BOLD, 15)
    pdf.drawRightString(width - MARGIN, y - 8, f"Factura #{invoice['id']}")

    pdf.setFont(FONT_REGULAR, 8)
    _set_color(pdf, COLOR_MUTED)
    pdf.drawRightString(width - MARGIN, y - 25, str(invoice["order_date"]))

    _set_color(pdf, COLOR_TEXT)

    return y - 112


def _draw_invoice_info(pdf: canvas.Canvas, invoice: dict, y: float) -> float:
    _set_color(pdf, COLOR_TEXT)

    pdf.setFont(FONT_BOLD, 15)
    pdf.drawString(MARGIN, y, f"Cliente: {invoice['client_name']}")
    y -= 23

    customer_fields = [
        ("CUIT", invoice.get("customer_cuit")),
        ("Dirección", invoice.get("customer_address")),
    ]

    pdf.setFont(FONT_REGULAR, 11)
    for label, value in customer_fields:
        text = str(value or "").strip()
        if not text:
            continue
        pdf.drawString(MARGIN, y, f"{label}: {text}")
        y -= 18

    transport = invoice.get("transport") or "Sin transporte"
    pdf.drawString(MARGIN, y, f"Transporte: {transport}")

    secondary_line = str(invoice.get("secondary_line") or "").strip()
    if secondary_line:
        y -= 18
        _set_color(pdf, COLOR_MUTED)
        pdf.drawString(MARGIN, y, secondary_line)
        _set_color(pdf, COLOR_TEXT)

    return y - 28


def _draw_items_header(pdf: canvas.Canvas, width: float, y: float) -> float:
    pdf.setFont(FONT_BOLD, 12)
    _set_color(pdf, COLOR_TEXT)

    pdf.drawString(MARGIN, y, "Producto")
    pdf.drawCentredString(MARGIN + 285, y, "Cant.")
    pdf.drawRightString(MARGIN + 405, y, "Precio")
    pdf.drawRightString(width - MARGIN, y, "Total")

    y -= 12
    _line(pdf, MARGIN, y, width - MARGIN)

    return y - 20


def _draw_item(pdf: canvas.Canvas, item: dict, width: float, y: float) -> float:
    font_size = 10.5

    pdf.setFont(FONT_REGULAR, font_size)
    _set_color(pdf, COLOR_TEXT)

    label = _truncate(
        str(item.get("label") or ""),
        FONT_REGULAR,
        font_size,
        max_width=260,
    )

    pdf.drawString(MARGIN, y, label)
    pdf.drawCentredString(MARGIN + 285, y, str(item.get("quantity") or 0))
    pdf.drawRightString(MARGIN + 405, y, _money(item.get("unit_price") or 0))
    pdf.drawRightString(width - MARGIN, y, _money(item.get("total") or 0))

    return y - 17


def _draw_totals(pdf: canvas.Canvas, invoice: dict, width: float, y: float) -> float:
    total_bultos = sum(
        int(item.get("quantity") or 0)
        for item in invoice.get("items", [])
    )

    discount_summary = _discount_summary(invoice)

    # Más separación antes de Bulto
    y -= 12

    # Bulto más grande y en negro
    pdf.setFont(FONT_BOLD, 12)
    _set_color(pdf, COLOR_TEXT)

    pdf.drawString(MARGIN, y, "Bulto")
    pdf.drawCentredString(MARGIN + 285, y, str(total_bultos))

    # Línea debajo de Bulto
    y -= 14
    _line(pdf, MARGIN, y, width - MARGIN)

    # Más aire antes del bloque de totales
    y -= 28

    _set_color(pdf, COLOR_TEXT)
    pdf.setFont(FONT_BOLD, 13)
    pdf.drawString(width - 200, y, "Bruto")
    pdf.drawRightString(width - MARGIN, y, _money(invoice.get("gross_total") or 0))

    y -= 24

    if int(invoice.get("discount_total") or 0) > 0:
        discount_label = (
            f"Descuento ({discount_summary})"
            if discount_summary != "Sin descuentos"
            else "Descuento"
        )

        pdf.setFont(FONT_REGULAR, 11)
        _set_color(pdf, COLOR_MUTED)
        pdf.drawString(width - 200, y, clean_cell_text(discount_label))
        pdf.drawRightString(width - MARGIN, y, _money(invoice.get("discount_total") or 0))

        y -= 20

    pdf.setFont(FONT_BOLD, 15)
    _set_color(pdf, COLOR_TEXT)
    pdf.drawString(width - 200, y, "Total")
    pdf.drawRightString(width - MARGIN, y, _money(invoice.get("final_total") or 0))

    return y - 20

def _draw_notes(pdf: canvas.Canvas, invoice: dict, y: float) -> float:
    notes = invoice.get("notes") or []

    if not notes:
        return y

    y -= 22

    pdf.setFont(FONT_BOLD, 10)
    _set_color(pdf, COLOR_TEXT)
    pdf.drawString(MARGIN, y, "Observaciones")

    pdf.setFont(FONT_REGULAR, 10)
    _set_color(pdf, COLOR_MUTED)

    for note in notes:
        y -= 15
        pdf.drawString(MARGIN, y, f"- {note}")

    _set_color(pdf, COLOR_TEXT)

    return y


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

    for item in invoice.get("items", []):
        if y < 120:
            y = _new_page(pdf, invoice, width, height)

        y = _draw_item(pdf, item, width, y)

    y = _draw_totals(pdf, invoice, width, y)
    _draw_notes(pdf, invoice, y)

    pdf.save()

    return buffer.getvalue()

from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageChops
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from ..core.utils import clean_cell_text
from ..dependencies import BASE_DIR


def _money(value: int | float) -> str:
    return f"$ {int(round(value or 0)):,}".replace(",", ".")


def _discount_summary(invoice: dict) -> str:
    line_discounts = invoice.get("line_discounts_by_format") or {}
    if line_discounts:
        rates = sorted({round(float(rate) * 100, 2) for rate in line_discounts.values() if float(rate) > 0})
        return " + ".join(f"{rate:g}%" for rate in rates) or "Sin descuentos"

    footer_discounts = invoice.get("footer_discounts") or []
    rates = [round(float(item.get("rate") or 0) * 100, 2) for item in footer_discounts if float(item.get("rate") or 0) > 0]
    return " + ".join(f"{rate:g}%" for rate in rates) or "Sin descuentos"


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
    pdf.drawImage(ImageReader(image_buffer), margin, y - logo_height, width=logo_width, height=logo_height, preserveAspectRatio=False, mask='auto')
    return y


def build_invoice_pdf(invoice: dict) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    margin = 36
    y = height - 28
    logo_path = BASE_DIR / "img" / "logo-bw.png"

    pdf.setTitle(f"Factura {invoice['id']}")

    _draw_logo(pdf, margin=margin, y=y, logo_path=logo_path)
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawRightString(width - margin, y - 8, f"Factura #{invoice['id']}")
    y -= 118

    pdf.setFont("Helvetica", 10)
    pdf.drawString(margin, y, f"Fecha: {invoice['order_date']}")
    pdf.drawString(margin + 180, y, f"Cliente: {invoice['client_name']}")
    y -= 18
    pdf.drawString(margin, y, f"Transporte: {invoice.get('transport') or 'Sin transporte'}")
    secondary_line = str(invoice.get("secondary_line") or "").strip()
    if secondary_line:
        y -= 18
        pdf.drawString(margin, y, secondary_line)
    discount_summary = _discount_summary(invoice)
    y -= 24

    headers = [
        ("Producto", margin),
        ("Cant.", margin + 275),
        ("Precio", margin + 345),
        ("Total", width - margin - 55),
    ]
    pdf.setFont("Helvetica-Bold", 10)
    for label, pos_x in headers:
        if label == "Cant.":
            pdf.drawCentredString(pos_x, y, label)
        else:
            pdf.drawString(pos_x, y, label)
    y -= 8
    pdf.line(margin, y, width - margin, y)
    y -= 16

    pdf.setFont("Helvetica", 10)
    for item in invoice.get("items", []):
        if y < 110:
            pdf.showPage()
            y = height - margin
            _draw_logo(pdf, margin=margin, y=y, logo_path=logo_path)
            pdf.setFont("Helvetica", 10)
            y -= 84
        label = str(item.get("label") or "")
        if stringWidth(label, "Helvetica", 10) > 260:
            label = f"{label[:45]}..."
        pdf.drawString(margin, y, label)
        pdf.drawCentredString(margin + 285, y, str(item.get("quantity") or 0))
        pdf.drawRightString(margin + 405, y, _money(item.get("unit_price") or 0))
        pdf.drawRightString(width - margin, y, _money(item.get("total") or 0))
        y -= 16

    y -= 10
    pdf.line(margin, y, width - margin, y)
    y -= 26
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(width - 200, y, "Bruto")
    pdf.drawRightString(width - margin, y, _money(invoice.get("gross_total") or 0))
    y -= 24
    if int(invoice.get("discount_total") or 0) > 0:
        discount_label = f"Descuento ({discount_summary})" if discount_summary != "Sin descuentos" else "Descuento"
        pdf.drawString(width - 200, y, clean_cell_text(discount_label))
        pdf.drawRightString(width - margin, y, _money(invoice.get("discount_total") or 0))
        y -= 17
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(width - 200, y, "Total")
    pdf.drawRightString(width - margin, y, _money(invoice.get("final_total") or 0))

    notes = invoice.get("notes") or []
    if notes:
        y -= 28
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(margin, y, "Observaciones")
        pdf.setFont("Helvetica", 10)
        for note in notes:
            y -= 16
            pdf.drawString(margin, y, f"- {note}")

    pdf.save()
    return buffer.getvalue()

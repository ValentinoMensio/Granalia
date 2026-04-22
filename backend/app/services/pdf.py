from __future__ import annotations

from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas


def _money(value: int | float) -> str:
    return f"$ {int(round(value or 0)):,}".replace(",", ".")


def build_invoice_pdf(invoice: dict) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    margin = 40
    y = height - margin

    pdf.setTitle(f"Factura {invoice['id']}")

    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(margin, y, "Granalia")
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawRightString(width - margin, y, f"Factura #{invoice['id']}")
    y -= 28

    pdf.setFont("Helvetica", 10)
    pdf.drawString(margin, y, f"Fecha: {invoice['order_date']}")
    pdf.drawString(margin + 180, y, f"Cliente: {invoice['client_name']}")
    y -= 18
    pdf.drawString(margin, y, f"Transporte: {invoice.get('transport') or 'Sin transporte'}")
    secondary_line = str(invoice.get("secondary_line") or "").strip()
    if secondary_line:
        y -= 18
        pdf.drawString(margin, y, secondary_line)
    y -= 24

    headers = [
        ("Producto", margin),
        ("Cant.", margin + 275),
        ("Precio", margin + 345),
        ("Total", width - margin - 55),
    ]
    pdf.setFont("Helvetica-Bold", 10)
    for label, pos_x in headers:
        pdf.drawString(pos_x, y, label)
    y -= 8
    pdf.line(margin, y, width - margin, y)
    y -= 16

    pdf.setFont("Helvetica", 10)
    for item in invoice.get("items", []):
        if y < 110:
            pdf.showPage()
            y = height - margin
            pdf.setFont("Helvetica", 10)
        label = str(item.get("label") or "")
        if stringWidth(label, "Helvetica", 10) > 260:
            label = f"{label[:45]}..."
        pdf.drawString(margin, y, label)
        pdf.drawRightString(margin + 315, y, str(item.get("quantity") or 0))
        pdf.drawRightString(margin + 405, y, _money(item.get("unit_price") or 0))
        pdf.drawRightString(width - margin, y, _money(item.get("total") or 0))
        y -= 16

    y -= 10
    pdf.line(width - 220, y, width - margin, y)
    y -= 18
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(width - 200, y, "Bruto")
    pdf.drawRightString(width - margin, y, _money(invoice.get("gross_total") or 0))
    y -= 16
    pdf.drawString(width - 200, y, "Descuento")
    pdf.drawRightString(width - margin, y, _money(invoice.get("discount_total") or 0))
    y -= 16
    pdf.setFont("Helvetica-Bold", 11)
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

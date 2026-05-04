"""Add historical invoice snapshots.

Revision ID: f6e7d8c9b0a1
Revises: d3f1a9b2c4e8
Create Date: 2026-05-04 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f6e7d8c9b0a1"
down_revision: Union[str, Sequence[str], None] = "d3f1a9b2c4e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE product_offerings ADD COLUMN IF NOT EXISTS net_weight_kg NUMERIC(12, 3) NOT NULL DEFAULT 0")
    op.add_column("invoices", sa.Column("price_list_effective_date", sa.DateTime(timezone=True), nullable=True))
    op.add_column("invoices", sa.Column("customer_cuit", sa.String(length=32), nullable=True))
    op.add_column("invoices", sa.Column("customer_address", sa.Text(), nullable=True))
    op.add_column("invoices", sa.Column("customer_business_name", sa.String(length=255), nullable=True))
    op.add_column("invoices", sa.Column("customer_email", sa.String(length=255), nullable=True))
    op.add_column("invoice_items", sa.Column("product_name", sa.String(length=255), nullable=True))
    op.add_column("invoice_items", sa.Column("offering_label", sa.String(length=120), nullable=True))
    op.add_column("invoice_items", sa.Column("offering_net_weight_kg", sa.Numeric(12, 3), nullable=True))
    op.add_column("invoice_items", sa.Column("line_type", sa.String(length=20), nullable=True))
    op.add_column("invoice_items", sa.Column("discount_rate", sa.Numeric(8, 6), nullable=True))

    op.execute(
        """
        UPDATE invoices i
        SET
            customer_cuit = COALESCE(c.cuit, ''),
            customer_address = COALESCE(c.address, ''),
            customer_business_name = COALESCE(c.business_name, ''),
            customer_email = COALESCE(c.email, '')
        FROM customers c
        WHERE i.customer_id = c.id
        """
    )
    op.execute(
        """
        UPDATE invoices i
        SET price_list_effective_date = COALESCE(i.price_list_effective_date, p.uploaded_at)
        FROM price_lists p
        WHERE i.price_list_id = p.id
        """
    )
    op.execute(
        """
        UPDATE invoice_items ii
        SET
            product_name = COALESCE(p.name, ''),
            offering_label = COALESCE(po.label, ''),
            offering_net_weight_kg = COALESCE(po.net_weight_kg, 0),
            line_type = CASE WHEN ii.unit_price = 0 THEN 'bonus' ELSE 'sale' END,
            discount_rate = CASE
                WHEN ii.gross > 0 AND ii.discount > 0 THEN ROUND((ii.discount::numeric / ii.gross::numeric), 6)
                ELSE 0
            END
        FROM products p, product_offerings po
        WHERE ii.product_id = p.id
          AND ii.offering_id = po.id
        """
    )
    op.execute("UPDATE invoice_items SET line_type = CASE WHEN unit_price = 0 THEN 'bonus' ELSE 'sale' END WHERE line_type IS NULL")
    op.execute("UPDATE invoice_items SET discount_rate = 0 WHERE discount_rate IS NULL")
    op.alter_column("invoice_items", "line_type", nullable=False, server_default=sa.text("'sale'"))

    op.create_check_constraint("ck_invoices_customer_cuit_max_length", "invoices", "char_length(customer_cuit) <= 32")
    op.create_check_constraint("ck_invoices_customer_address_max_length", "invoices", "char_length(customer_address) <= 500")
    op.create_check_constraint("ck_invoices_customer_business_name_max_length", "invoices", "char_length(customer_business_name) <= 255")
    op.create_check_constraint("ck_invoices_customer_email_max_length", "invoices", "char_length(customer_email) <= 255")
    op.create_check_constraint("ck_invoice_items_product_name_max_length", "invoice_items", "char_length(product_name) <= 255")
    op.create_check_constraint("ck_invoice_items_offering_label_max_length", "invoice_items", "char_length(offering_label) <= 120")
    op.create_check_constraint("ck_invoice_items_offering_net_weight_nonnegative", "invoice_items", "offering_net_weight_kg >= 0")
    op.create_check_constraint("ck_invoice_items_line_type_valid", "invoice_items", "line_type IN ('sale', 'bonus')")
    op.create_check_constraint("ck_invoice_items_discount_rate_range", "invoice_items", "discount_rate >= 0 AND discount_rate <= 1")


def downgrade() -> None:
    op.drop_constraint("ck_invoice_items_discount_rate_range", table_name="invoice_items", type_="check")
    op.drop_constraint("ck_invoice_items_line_type_valid", table_name="invoice_items", type_="check")
    op.alter_column("invoice_items", "line_type", nullable=True, server_default=None)
    op.drop_constraint("ck_invoice_items_offering_net_weight_nonnegative", table_name="invoice_items", type_="check")
    op.drop_constraint("ck_invoice_items_offering_label_max_length", table_name="invoice_items", type_="check")
    op.drop_constraint("ck_invoice_items_product_name_max_length", table_name="invoice_items", type_="check")
    op.drop_constraint("ck_invoices_customer_email_max_length", table_name="invoices", type_="check")
    op.drop_constraint("ck_invoices_customer_business_name_max_length", table_name="invoices", type_="check")
    op.drop_constraint("ck_invoices_customer_address_max_length", table_name="invoices", type_="check")
    op.drop_constraint("ck_invoices_customer_cuit_max_length", table_name="invoices", type_="check")
    op.drop_column("invoice_items", "discount_rate")
    op.drop_column("invoice_items", "line_type")
    op.drop_column("invoice_items", "offering_net_weight_kg")
    op.drop_column("invoice_items", "offering_label")
    op.drop_column("invoice_items", "product_name")
    op.drop_column("invoices", "customer_email")
    op.drop_column("invoices", "customer_business_name")
    op.drop_column("invoices", "customer_address")
    op.drop_column("invoices", "customer_cuit")
    op.drop_column("invoices", "price_list_effective_date")

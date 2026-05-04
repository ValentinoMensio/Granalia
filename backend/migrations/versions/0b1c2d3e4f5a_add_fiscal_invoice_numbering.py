"""Add fiscal invoice numbering.

Revision ID: 0b1c2d3e4f5a
Revises: f6e7d8c9b0a1
Create Date: 2026-05-04 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0b1c2d3e4f5a"
down_revision: Union[str, Sequence[str], None] = "f6e7d8c9b0a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "invoice_sequences",
        sa.Column("document_type", sa.String(length=30), nullable=False),
        sa.Column("point_of_sale", sa.Integer(), nullable=False),
        sa.Column("next_number", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("char_length(btrim(document_type)) > 0", name="ck_invoice_sequences_document_type_not_blank"),
        sa.CheckConstraint("point_of_sale > 0", name="ck_invoice_sequences_point_of_sale_positive"),
        sa.CheckConstraint("next_number > 0", name="ck_invoice_sequences_next_number_positive"),
        sa.UniqueConstraint("document_type", "point_of_sale", name="uq_invoice_sequences_scope"),
    )

    op.add_column("invoices", sa.Column("document_type", sa.String(length=30), nullable=True))
    op.add_column("invoices", sa.Column("point_of_sale", sa.Integer(), nullable=True))
    op.add_column("invoices", sa.Column("invoice_number", sa.BigInteger(), nullable=True))

    op.execute(
        """
        WITH numbered AS (
            SELECT id, row_number() OVER (ORDER BY created_at, id) AS number
            FROM invoices
        )
        UPDATE invoices i
        SET
            document_type = 'FACTURA',
            point_of_sale = 1,
            invoice_number = numbered.number
        FROM numbered
        WHERE i.id = numbered.id
        """
    )
    op.execute(
        """
        INSERT INTO invoice_sequences (document_type, point_of_sale, next_number, created_at, updated_at)
        SELECT 'FACTURA', 1, COALESCE(MAX(invoice_number), 0) + 1, now(), now()
        FROM invoices
        """
    )

    op.alter_column("invoices", "document_type", nullable=False, server_default=sa.text("'FACTURA'"))
    op.alter_column("invoices", "point_of_sale", nullable=False, server_default=sa.text("1"))
    op.alter_column("invoices", "invoice_number", nullable=False)
    op.create_check_constraint("ck_invoices_document_type_not_blank", "invoices", "char_length(btrim(document_type)) > 0")
    op.create_check_constraint("ck_invoices_point_of_sale_positive", "invoices", "point_of_sale > 0")
    op.create_check_constraint("ck_invoices_invoice_number_positive", "invoices", "invoice_number > 0")
    op.create_unique_constraint("uq_invoices_fiscal_number", "invoices", ["document_type", "point_of_sale", "invoice_number"])


def downgrade() -> None:
    op.drop_constraint("uq_invoices_fiscal_number", table_name="invoices", type_="unique")
    op.drop_constraint("ck_invoices_invoice_number_positive", table_name="invoices", type_="check")
    op.drop_constraint("ck_invoices_point_of_sale_positive", table_name="invoices", type_="check")
    op.drop_constraint("ck_invoices_document_type_not_blank", table_name="invoices", type_="check")
    op.drop_column("invoices", "invoice_number")
    op.drop_column("invoices", "point_of_sale")
    op.drop_column("invoices", "document_type")
    op.drop_table("invoice_sequences")

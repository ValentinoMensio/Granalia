"""Split internal and ARCA invoice numbers.

Revision ID: 4c5d6e7f8a9b
Revises: 3b4c5d6e7f8a
Create Date: 2026-05-06 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "4c5d6e7f8a9b"
down_revision: Union[str, Sequence[str], None] = "3b4c5d6e7f8a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("invoices", sa.Column("internal_invoice_number", sa.BigInteger(), nullable=True))
    op.execute("UPDATE invoices SET document_type = regexp_replace(document_type, '_DRAFT$', '') WHERE right(document_type, 6) = '_DRAFT'")
    op.execute("UPDATE invoices SET internal_invoice_number = invoice_number WHERE fiscal_status = 'internal' AND internal_invoice_number IS NULL")
    op.execute("UPDATE invoices SET fiscal_status = 'authorized' WHERE arca_cae IS NOT NULL AND arca_invoice_number IS NOT NULL AND fiscal_status <> 'authorized'")
    op.execute("ALTER TABLE invoices DROP CONSTRAINT IF EXISTS uq_invoices_fiscal_number")
    op.alter_column("invoices", "invoice_number", existing_type=sa.BigInteger(), nullable=True)
    op.execute("ALTER TABLE invoices DROP CONSTRAINT IF EXISTS ck_invoices_invoice_number_positive")
    op.create_check_constraint("ck_invoices_invoice_number_positive", "invoices", "invoice_number IS NULL OR invoice_number > 0")
    op.execute("ALTER TABLE invoices DROP CONSTRAINT IF EXISTS ck_invoices_fiscal_status_valid")
    op.create_check_constraint("ck_invoices_fiscal_status_valid", "invoices", "fiscal_status IN ('internal', 'draft', 'authorizing', 'authorized', 'rejected', 'error')")
    op.create_check_constraint("ck_invoices_internal_invoice_number_positive", "invoices", "internal_invoice_number IS NULL OR internal_invoice_number > 0")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_invoices_internal_number ON invoices (document_type, point_of_sale, internal_invoice_number) WHERE internal_invoice_number IS NOT NULL")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_invoices_arca_number ON invoices (arca_environment, arca_cbte_tipo, arca_point_of_sale, arca_invoice_number) WHERE arca_invoice_number IS NOT NULL")
    op.execute(
        """
        INSERT INTO invoice_sequences (document_type, point_of_sale, next_number, created_at, updated_at)
        SELECT document_type || '_INTERNAL', point_of_sale, COALESCE(MAX(internal_invoice_number), 0) + 1, now(), now()
        FROM invoices
        WHERE internal_invoice_number IS NOT NULL
        GROUP BY document_type, point_of_sale
        ON CONFLICT (document_type, point_of_sale) DO UPDATE
        SET next_number = GREATEST(invoice_sequences.next_number, EXCLUDED.next_number),
            updated_at = now()
        """
    )

def downgrade() -> None:
    op.drop_index("uq_invoices_arca_number", table_name="invoices")
    op.drop_index("uq_invoices_internal_number", table_name="invoices")
    op.drop_constraint("ck_invoices_fiscal_status_valid", "invoices", type_="check")
    op.create_check_constraint("ck_invoices_fiscal_status_valid", "invoices", "fiscal_status IN ('internal', 'draft', 'authorized', 'rejected', 'error')")
    op.drop_constraint("ck_invoices_internal_invoice_number_positive", "invoices", type_="check")
    op.create_unique_constraint("uq_invoices_fiscal_number", "invoices", ["document_type", "point_of_sale", "invoice_number"])
    op.alter_column("invoices", "invoice_number", existing_type=sa.BigInteger(), nullable=False)
    op.drop_column("invoices", "internal_invoice_number")

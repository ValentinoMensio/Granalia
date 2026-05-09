"""Remove invoice XLSX storage.

Revision ID: 6e7f8a9b0c1d
Revises: 5d6e7f8a9b0c
Create Date: 2026-05-09 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "6e7f8a9b0c1d"
down_revision: Union[str, Sequence[str], None] = "5d6e7f8a9b0c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE invoices DROP CONSTRAINT IF EXISTS ck_invoices_xlsx_size_matches")
    op.execute("ALTER TABLE invoices DROP CONSTRAINT IF EXISTS ck_invoices_xlsx_size_positive")
    op.execute("ALTER TABLE invoices DROP CONSTRAINT IF EXISTS ck_invoices_output_filename_not_blank")
    op.drop_column("invoices", "xlsx_size")
    op.drop_column("invoices", "xlsx_data")
    op.drop_column("invoices", "output_filename")


def downgrade() -> None:
    op.add_column("invoices", sa.Column("output_filename", sa.String(length=255), nullable=False, server_default="sin-xlsx.xlsx"))
    op.add_column("invoices", sa.Column("xlsx_data", sa.LargeBinary(), nullable=False, server_default=sa.text("'\\x00'::bytea")))
    op.add_column("invoices", sa.Column("xlsx_size", sa.Integer(), nullable=False, server_default="1"))
    op.create_check_constraint("ck_invoices_output_filename_not_blank", "invoices", "char_length(btrim(output_filename)) > 0")
    op.create_check_constraint("ck_invoices_xlsx_size_positive", "invoices", "xlsx_size > 0")
    op.create_check_constraint("ck_invoices_xlsx_size_matches", "invoices", "octet_length(xlsx_data) = xlsx_size")
    op.alter_column("invoices", "output_filename", server_default=None)
    op.alter_column("invoices", "xlsx_data", server_default=None)
    op.alter_column("invoices", "xlsx_size", server_default=None)

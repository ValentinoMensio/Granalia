"""Add invoice customer IVA condition.

Revision ID: 5d6e7f8a9b0c
Revises: 4c5d6e7f8a9b
Create Date: 2026-05-07 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "5d6e7f8a9b0c"
down_revision: Union[str, Sequence[str], None] = "4c5d6e7f8a9b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("invoices", sa.Column("customer_iva_condition", sa.String(length=120), nullable=False, server_default=""))
    op.create_check_constraint("ck_invoices_customer_iva_condition_max_length", "invoices", "char_length(customer_iva_condition) <= 120")


def downgrade() -> None:
    op.drop_constraint("ck_invoices_customer_iva_condition_max_length", table_name="invoices", type_="check")
    op.drop_column("invoices", "customer_iva_condition")

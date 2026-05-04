"""Allow fractional invoice quantities.

Revision ID: 91d4e3a6b8c2
Revises: 2f4e9a7c1b23
Create Date: 2026-04-29 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "91d4e3a6b8c2"
down_revision: Union[str, Sequence[str], None] = "2f4e9a7c1b23"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("invoice_items", "quantity", type_=sa.Numeric(12, 2), postgresql_using="quantity::numeric")
    op.alter_column("invoices", "total_bultos", type_=sa.Numeric(12, 2), postgresql_using="total_bultos::numeric")


def downgrade() -> None:
    op.alter_column("invoice_items", "quantity", type_=sa.Integer(), postgresql_using="round(quantity)::integer")
    op.alter_column("invoices", "total_bultos", type_=sa.Integer(), postgresql_using="round(total_bultos)::integer")

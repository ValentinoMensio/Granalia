"""Add ARCA IVA condition cache and fiscal customer snapshot.

Revision ID: 9b0c1d2e3f4a
Revises: 8a9b0c1d2e3f
Create Date: 2026-05-25 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "9b0c1d2e3f4a"
down_revision: Union[str, Sequence[str], None] = "8a9b0c1d2e3f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "arca_iva_conditions",
        sa.Column("arca_id", sa.Integer(), primary_key=True),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("normalized_description", sa.String(length=255), nullable=False, unique=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("arca_id > 0", name="ck_arca_iva_conditions_id_positive"),
        sa.CheckConstraint("char_length(btrim(description)) > 0", name="ck_arca_iva_conditions_description_not_blank"),
        sa.CheckConstraint("char_length(btrim(normalized_description)) > 0", name="ck_arca_iva_conditions_normalized_not_blank"),
    )
    op.add_column("invoices", sa.Column("customer_fiscal_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("invoices", "customer_fiscal_snapshot")
    op.drop_table("arca_iva_conditions")

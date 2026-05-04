"""Add automatic bonus rules to customers.

Revision ID: b7d4c2e91a30
Revises: 8f3d2c1a9b44
Create Date: 2026-04-28 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "b7d4c2e91a30"
down_revision: Union[str, Sequence[str], None] = "8f3d2c1a9b44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "customers",
        sa.Column(
            "automatic_bonus_rules",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )
    op.create_check_constraint(
        "ck_customers_automatic_bonus_rules_array",
        "customers",
        "jsonb_typeof(automatic_bonus_rules) = 'array'",
    )
    op.create_check_constraint(
        "ck_customers_automatic_bonus_rules_max_items",
        "customers",
        "CASE WHEN jsonb_typeof(automatic_bonus_rules) = 'array' THEN jsonb_array_length(automatic_bonus_rules) <= 100 ELSE false END",
    )


def downgrade() -> None:
    op.drop_constraint("ck_customers_automatic_bonus_rules_max_items", table_name="customers", type_="check")
    op.drop_constraint("ck_customers_automatic_bonus_rules_array", table_name="customers", type_="check")
    op.drop_column("customers", "automatic_bonus_rules")

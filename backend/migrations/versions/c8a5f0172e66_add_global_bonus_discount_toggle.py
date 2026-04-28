"""Add global bonus discount toggle to customers.

Revision ID: c8a5f0172e66
Revises: b7d4c2e91a30
Create Date: 2026-04-28 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c8a5f0172e66"
down_revision: Union[str, Sequence[str], None] = "b7d4c2e91a30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "customers",
        sa.Column("automatic_bonus_disables_line_discount", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("customers", "automatic_bonus_disables_line_discount")

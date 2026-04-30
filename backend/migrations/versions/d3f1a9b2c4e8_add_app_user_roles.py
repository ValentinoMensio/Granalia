"""Add roles to application users.

Revision ID: d3f1a9b2c4e8
Revises: a4b9c8d7e6f5
Create Date: 2026-04-30 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d3f1a9b2c4e8"
down_revision: Union[str, Sequence[str], None] = "a4b9c8d7e6f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("app_users", sa.Column("role", sa.String(length=20), nullable=False, server_default="admin"))
    op.create_check_constraint("ck_app_users_role_valid", "app_users", "role IN ('admin', 'operator')")


def downgrade() -> None:
    op.drop_constraint("ck_app_users_role_valid", table_name="app_users", type_="check")
    op.drop_column("app_users", "role")

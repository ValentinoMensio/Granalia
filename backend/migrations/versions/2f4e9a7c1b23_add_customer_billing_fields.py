"""Add customer billing fields.

Revision ID: 2f4e9a7c1b23
Revises: c8a5f0172e66
Create Date: 2026-04-28 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "2f4e9a7c1b23"
down_revision: Union[str, Sequence[str], None] = "c8a5f0172e66"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("customers", sa.Column("cuit", sa.String(length=32), nullable=False, server_default=""))
    op.add_column("customers", sa.Column("address", sa.Text(), nullable=False, server_default=""))
    op.add_column("customers", sa.Column("business_name", sa.String(length=255), nullable=False, server_default=""))
    op.add_column("customers", sa.Column("email", sa.String(length=255), nullable=False, server_default=""))
    op.create_check_constraint("ck_customers_cuit_max_length", "customers", "char_length(cuit) <= 32")
    op.create_check_constraint("ck_customers_address_max_length", "customers", "char_length(address) <= 500")
    op.create_check_constraint("ck_customers_business_name_max_length", "customers", "char_length(business_name) <= 255")
    op.create_check_constraint("ck_customers_email_max_length", "customers", "char_length(email) <= 255")


def downgrade() -> None:
    op.drop_constraint("ck_customers_email_max_length", table_name="customers", type_="check")
    op.drop_constraint("ck_customers_business_name_max_length", table_name="customers", type_="check")
    op.drop_constraint("ck_customers_address_max_length", table_name="customers", type_="check")
    op.drop_constraint("ck_customers_cuit_max_length", table_name="customers", type_="check")
    op.drop_column("customers", "email")
    op.drop_column("customers", "business_name")
    op.drop_column("customers", "address")
    op.drop_column("customers", "cuit")

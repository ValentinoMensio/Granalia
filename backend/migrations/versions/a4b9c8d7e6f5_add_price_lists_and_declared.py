"""Add multiple price lists and invoice declared flag.

Revision ID: a4b9c8d7e6f5
Revises: 91d4e3a6b8c2
Create Date: 2026-04-29 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a4b9c8d7e6f5"
down_revision: Union[str, Sequence[str], None] = "91d4e3a6b8c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("price_lists", sa.Column("name", sa.String(length=255), nullable=False, server_default="Lista principal"))
    op.create_check_constraint("ck_price_lists_name_not_blank", "price_lists", "char_length(btrim(name)) > 0")
    op.add_column("catalogs", sa.Column("price_list_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key("fk_catalogs_price_list_id", "catalogs", "price_lists", ["price_list_id"], ["id"], ondelete="SET NULL")
    op.add_column("invoices", sa.Column("price_list_id", sa.BigInteger(), nullable=True))
    op.add_column("invoices", sa.Column("declared", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("invoices", sa.Column("price_list_name", sa.String(length=255), nullable=False, server_default=""))
    op.create_foreign_key("fk_invoices_price_list_id", "invoices", "price_lists", ["price_list_id"], ["id"], ondelete="SET NULL")
    op.execute("""
        UPDATE catalogs c
        SET price_list_id = p.id
        FROM price_lists p
        WHERE c.active = true AND p.active = true
    """)
    op.execute("""
        UPDATE invoices i
        SET price_list_id = p.id,
            price_list_name = p.name
        FROM price_lists p
        WHERE p.active = true
          AND COALESCE(i.price_list_name, '') = ''
    """)


def downgrade() -> None:
    op.drop_constraint("fk_invoices_price_list_id", "invoices", type_="foreignkey")
    op.drop_column("invoices", "price_list_name")
    op.drop_column("invoices", "declared")
    op.drop_column("invoices", "price_list_id")
    op.drop_constraint("fk_catalogs_price_list_id", "catalogs", type_="foreignkey")
    op.drop_column("catalogs", "price_list_id")
    op.drop_constraint("ck_price_lists_name_not_blank", "price_lists", type_="check")
    op.drop_column("price_lists", "name")

"""Add ARCA request audit table.

Revision ID: 3b4c5d6e7f8a
Revises: 1a2b3c4d5e6f
Create Date: 2026-05-05 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "3b4c5d6e7f8a"
down_revision: Union[str, Sequence[str], None] = "1a2b3c4d5e6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "arca_requests",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("invoice_id", sa.BigInteger(), nullable=False),
        sa.Column("operation", sa.String(length=80), nullable=False),
        sa.Column("environment", sa.String(length=20), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("sanitized_request", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("sanitized_response", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_code", sa.String(length=50), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("char_length(btrim(operation)) > 0", name="ck_arca_requests_operation_not_blank"),
        sa.CheckConstraint("environment IN ('homologacion', 'produccion')", name="ck_arca_requests_environment_valid"),
        sa.CheckConstraint("char_length(btrim(request_hash)) > 0", name="ck_arca_requests_request_hash_not_blank"),
        sa.CheckConstraint("status IN ('pending', 'authorized', 'rejected', 'error')", name="ck_arca_requests_status_valid"),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("arca_requests")

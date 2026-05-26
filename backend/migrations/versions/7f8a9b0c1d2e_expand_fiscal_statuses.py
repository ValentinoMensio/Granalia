"""Expand fiscal invoice statuses.

Revision ID: 7f8a9b0c1d2e
Revises: 6e7f8a9b0c1d
Create Date: 2026-05-25 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "7f8a9b0c1d2e"
down_revision: Union[str, Sequence[str], None] = "6e7f8a9b0c1d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE invoices DROP CONSTRAINT IF EXISTS ck_invoices_fiscal_status_valid")
    op.create_check_constraint(
        "ck_invoices_fiscal_status_valid",
        "invoices",
        "fiscal_status IN ('internal', 'draft', 'authorizing', 'authorized', 'authorized_homologation', 'authorization_failed', 'rejected', 'error')",
    )


def downgrade() -> None:
    op.execute("UPDATE invoices SET fiscal_status = 'error' WHERE fiscal_status = 'authorization_failed'")
    op.execute("UPDATE invoices SET fiscal_status = 'draft' WHERE fiscal_status = 'authorized_homologation'")
    op.execute("ALTER TABLE invoices DROP CONSTRAINT IF EXISTS ck_invoices_fiscal_status_valid")
    op.create_check_constraint(
        "ck_invoices_fiscal_status_valid",
        "invoices",
        "fiscal_status IN ('internal', 'draft', 'authorizing', 'authorized', 'rejected', 'error')",
    )

"""Add ARCA request idempotency fields.

Revision ID: 8a9b0c1d2e3f
Revises: 7f8a9b0c1d2e
Create Date: 2026-05-25 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "8a9b0c1d2e3f"
down_revision: Union[str, Sequence[str], None] = "7f8a9b0c1d2e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("arca_requests", sa.Column("issuer_cuit", sa.String(length=32), nullable=True))
    op.add_column("arca_requests", sa.Column("point_of_sale", sa.Integer(), nullable=True))
    op.add_column("arca_requests", sa.Column("cbte_tipo", sa.Integer(), nullable=True))
    op.add_column("arca_requests", sa.Column("cbte_number", sa.BigInteger(), nullable=True))
    op.add_column("arca_requests", sa.Column("idempotency_key", sa.String(length=120), nullable=True))
    op.add_column("arca_requests", sa.Column("soap_action", sa.String(length=120), nullable=True))
    op.add_column("arca_requests", sa.Column("retry_of", sa.BigInteger(), nullable=True))
    op.add_column("arca_requests", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE arca_requests SET updated_at = created_at WHERE updated_at IS NULL")
    op.alter_column("arca_requests", "updated_at", nullable=False)
    op.create_foreign_key("fk_arca_requests_retry_of", "arca_requests", "arca_requests", ["retry_of"], ["id"], ondelete="SET NULL")
    op.create_check_constraint("ck_arca_requests_point_of_sale_positive", "arca_requests", "point_of_sale IS NULL OR point_of_sale > 0")
    op.create_check_constraint("ck_arca_requests_cbte_number_positive", "arca_requests", "cbte_number IS NULL OR cbte_number > 0")
    op.execute("ALTER TABLE arca_requests DROP CONSTRAINT IF EXISTS ck_arca_requests_status_valid")
    op.create_check_constraint("ck_arca_requests_status_valid", "arca_requests", "status IN ('pending', 'authorized', 'rejected', 'authorization_failed', 'error')")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_arca_requests_reserved_number ON arca_requests (environment, issuer_cuit, point_of_sale, cbte_tipo, cbte_number) WHERE cbte_number IS NOT NULL")


def downgrade() -> None:
    op.drop_index("uq_arca_requests_reserved_number", table_name="arca_requests")
    op.execute("UPDATE arca_requests SET status = 'error' WHERE status = 'authorization_failed'")
    op.execute("ALTER TABLE arca_requests DROP CONSTRAINT IF EXISTS ck_arca_requests_status_valid")
    op.create_check_constraint("ck_arca_requests_status_valid", "arca_requests", "status IN ('pending', 'authorized', 'rejected', 'error')")
    op.drop_constraint("ck_arca_requests_cbte_number_positive", "arca_requests", type_="check")
    op.drop_constraint("ck_arca_requests_point_of_sale_positive", "arca_requests", type_="check")
    op.drop_constraint("fk_arca_requests_retry_of", "arca_requests", type_="foreignkey")
    for column_name in ("updated_at", "retry_of", "soap_action", "idempotency_key", "cbte_number", "cbte_tipo", "point_of_sale", "issuer_cuit"):
        op.drop_column("arca_requests", column_name)

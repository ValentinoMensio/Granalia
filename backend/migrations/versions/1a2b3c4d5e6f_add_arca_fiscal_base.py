"""Add ARCA fiscal base structures.

Revision ID: 1a2b3c4d5e6f
Revises: 0b1c2d3e4f5a
Create Date: 2026-05-05 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "1a2b3c4d5e6f"
down_revision: Union[str, Sequence[str], None] = "0b1c2d3e4f5a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "invoice_batches",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("customer_id", sa.BigInteger(), nullable=True),
        sa.Column("client_name", sa.String(length=255), nullable=False),
        sa.Column("order_date", sa.Date(), nullable=False),
        sa.Column("billing_mode", sa.String(length=30), nullable=False),
        sa.Column("declared_percentage", sa.Numeric(5, 2), nullable=True),
        sa.Column("internal_percentage", sa.Numeric(5, 2), nullable=True),
        sa.Column("internal_price_list_id", sa.BigInteger(), nullable=True),
        sa.Column("fiscal_price_list_id", sa.BigInteger(), nullable=True),
        sa.Column("created_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("char_length(btrim(client_name)) > 0", name="ck_invoice_batches_client_name_not_blank"),
        sa.CheckConstraint("billing_mode IN ('internal_only', 'fiscal_only', 'split')", name="ck_invoice_batches_billing_mode_valid"),
        sa.CheckConstraint("declared_percentage IS NULL OR (declared_percentage >= 0 AND declared_percentage <= 100)", name="ck_invoice_batches_declared_percentage_range"),
        sa.CheckConstraint("internal_percentage IS NULL OR (internal_percentage >= 0 AND internal_percentage <= 100)", name="ck_invoice_batches_internal_percentage_range"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["internal_price_list_id"], ["price_lists.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["fiscal_price_list_id"], ["price_lists.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["app_users.id"], ondelete="SET NULL"),
    )

    op.add_column("products", sa.Column("iva_rate", sa.Numeric(5, 3), nullable=True))
    op.create_check_constraint("ck_products_iva_rate_valid", "products", "iva_rate IS NULL OR iva_rate IN (0.105, 0.210)")

    op.add_column("invoices", sa.Column("batch_id", sa.BigInteger(), nullable=True))
    op.add_column("invoices", sa.Column("split_kind", sa.String(length=20), nullable=True))
    op.add_column("invoices", sa.Column("split_percentage", sa.Numeric(5, 2), nullable=True))
    op.add_column("invoices", sa.Column("fiscal_status", sa.String(length=20), nullable=False, server_default="internal"))
    op.add_column("invoices", sa.Column("fiscal_locked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("invoices", sa.Column("fiscal_authorized_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("invoices", sa.Column("arca_environment", sa.String(length=20), nullable=True))
    op.add_column("invoices", sa.Column("arca_cuit_emisor", sa.String(length=32), nullable=True))
    op.add_column("invoices", sa.Column("arca_cbte_tipo", sa.Integer(), nullable=True))
    op.add_column("invoices", sa.Column("arca_concepto", sa.Integer(), nullable=True))
    op.add_column("invoices", sa.Column("arca_doc_tipo", sa.Integer(), nullable=True))
    op.add_column("invoices", sa.Column("arca_doc_nro", sa.String(length=32), nullable=True))
    op.add_column("invoices", sa.Column("arca_point_of_sale", sa.Integer(), nullable=True))
    op.add_column("invoices", sa.Column("arca_invoice_number", sa.BigInteger(), nullable=True))
    op.add_column("invoices", sa.Column("arca_cae", sa.String(length=32), nullable=True))
    op.add_column("invoices", sa.Column("arca_cae_expires_at", sa.Date(), nullable=True))
    op.add_column("invoices", sa.Column("arca_result", sa.String(length=20), nullable=True))
    op.add_column("invoices", sa.Column("arca_observations", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("invoices", sa.Column("arca_error_code", sa.String(length=50), nullable=True))
    op.add_column("invoices", sa.Column("arca_error_message", sa.Text(), nullable=True))
    op.add_column("invoices", sa.Column("arca_request_id", sa.String(length=120), nullable=True))
    op.create_foreign_key("fk_invoices_batch_id", "invoices", "invoice_batches", ["batch_id"], ["id"], ondelete="SET NULL")
    op.create_check_constraint("ck_invoices_split_kind_valid", "invoices", "split_kind IS NULL OR split_kind IN ('internal', 'fiscal')")
    op.create_check_constraint("ck_invoices_split_percentage_range", "invoices", "split_percentage IS NULL OR (split_percentage >= 0 AND split_percentage <= 100)")
    op.create_check_constraint("ck_invoices_fiscal_status_valid", "invoices", "fiscal_status IN ('internal', 'draft', 'authorized', 'rejected', 'error')")
    op.create_check_constraint("ck_invoices_arca_environment_valid", "invoices", "arca_environment IS NULL OR arca_environment IN ('homologacion', 'produccion')")
    op.create_check_constraint("ck_invoices_arca_point_of_sale_positive", "invoices", "arca_point_of_sale IS NULL OR arca_point_of_sale > 0")
    op.create_check_constraint("ck_invoices_arca_invoice_number_positive", "invoices", "arca_invoice_number IS NULL OR arca_invoice_number > 0")

    op.add_column("invoice_items", sa.Column("iva_rate", sa.Numeric(5, 3), nullable=True))
    op.add_column("invoice_items", sa.Column("net_amount", sa.Numeric(12, 2), nullable=True))
    op.add_column("invoice_items", sa.Column("iva_amount", sa.Numeric(12, 2), nullable=True))
    op.add_column("invoice_items", sa.Column("fiscal_total", sa.Numeric(12, 2), nullable=True))
    op.create_check_constraint("ck_invoice_items_iva_rate_valid", "invoice_items", "iva_rate IS NULL OR iva_rate IN (0.105, 0.210)")
    op.create_check_constraint("ck_invoice_items_net_amount_nonnegative", "invoice_items", "net_amount IS NULL OR net_amount >= 0")
    op.create_check_constraint("ck_invoice_items_iva_amount_nonnegative", "invoice_items", "iva_amount IS NULL OR iva_amount >= 0")
    op.create_check_constraint("ck_invoice_items_fiscal_total_nonnegative", "invoice_items", "fiscal_total IS NULL OR fiscal_total >= 0")

    op.create_table(
        "invoice_tax_breakdown",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("invoice_id", sa.BigInteger(), nullable=False),
        sa.Column("iva_rate", sa.Numeric(5, 3), nullable=False),
        sa.Column("arca_iva_id", sa.Integer(), nullable=False),
        sa.Column("base_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("iva_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("iva_rate IN (0.105, 0.210)", name="ck_invoice_tax_breakdown_iva_rate_valid"),
        sa.CheckConstraint("base_amount >= 0", name="ck_invoice_tax_breakdown_base_amount_nonnegative"),
        sa.CheckConstraint("iva_amount >= 0", name="ck_invoice_tax_breakdown_iva_amount_nonnegative"),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("invoice_id", "iva_rate", name="uq_invoice_tax_breakdown_invoice_rate"),
    )


def downgrade() -> None:
    op.drop_table("invoice_tax_breakdown")
    op.drop_constraint("ck_invoice_items_fiscal_total_nonnegative", table_name="invoice_items", type_="check")
    op.drop_constraint("ck_invoice_items_iva_amount_nonnegative", table_name="invoice_items", type_="check")
    op.drop_constraint("ck_invoice_items_net_amount_nonnegative", table_name="invoice_items", type_="check")
    op.drop_constraint("ck_invoice_items_iva_rate_valid", table_name="invoice_items", type_="check")
    op.drop_column("invoice_items", "fiscal_total")
    op.drop_column("invoice_items", "iva_amount")
    op.drop_column("invoice_items", "net_amount")
    op.drop_column("invoice_items", "iva_rate")

    op.drop_constraint("ck_invoices_arca_invoice_number_positive", table_name="invoices", type_="check")
    op.drop_constraint("ck_invoices_arca_point_of_sale_positive", table_name="invoices", type_="check")
    op.drop_constraint("ck_invoices_arca_environment_valid", table_name="invoices", type_="check")
    op.drop_constraint("ck_invoices_fiscal_status_valid", table_name="invoices", type_="check")
    op.drop_constraint("ck_invoices_split_percentage_range", table_name="invoices", type_="check")
    op.drop_constraint("ck_invoices_split_kind_valid", table_name="invoices", type_="check")
    op.drop_constraint("fk_invoices_batch_id", table_name="invoices", type_="foreignkey")
    for column_name in (
        "arca_request_id",
        "arca_error_message",
        "arca_error_code",
        "arca_observations",
        "arca_result",
        "arca_cae_expires_at",
        "arca_cae",
        "arca_invoice_number",
        "arca_point_of_sale",
        "arca_doc_nro",
        "arca_doc_tipo",
        "arca_concepto",
        "arca_cbte_tipo",
        "arca_cuit_emisor",
        "arca_environment",
        "fiscal_authorized_at",
        "fiscal_locked_at",
        "fiscal_status",
        "split_percentage",
        "split_kind",
        "batch_id",
    ):
        op.drop_column("invoices", column_name)

    op.drop_constraint("ck_products_iva_rate_valid", table_name="products", type_="check")
    op.drop_column("products", "iva_rate")
    op.drop_table("invoice_batches")

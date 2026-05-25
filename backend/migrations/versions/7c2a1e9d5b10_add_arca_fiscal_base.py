"""Add ARCA fiscal base fields.

Revision ID: 7c2a1e9d5b10
Revises: 0b1c2d3e4f5a
Create Date: 2026-05-25 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "7c2a1e9d5b10"
down_revision: Union[str, Sequence[str], None] = "0b1c2d3e4f5a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "arca_iva_rates",
        sa.Column("arca_id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("description", sa.String(length=120), nullable=False),
        sa.Column("percent", sa.Numeric(6, 3), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("arca_id > 0", name="ck_arca_iva_rates_arca_id_positive"),
        sa.CheckConstraint("char_length(btrim(description)) > 0", name="ck_arca_iva_rates_description_not_blank"),
        sa.CheckConstraint("percent >= 0", name="ck_arca_iva_rates_percent_nonnegative"),
    )
    op.execute(
        """
        INSERT INTO arca_iva_rates (arca_id, description, percent, active, created_at, updated_at)
        VALUES
            (4, 'IVA 10.5%', 10.500, true, now(), now()),
            (5, 'IVA 21%', 21.000, true, now(), now())
        ON CONFLICT (arca_id) DO NOTHING
        """
    )

    op.add_column("product_offerings", sa.Column("iva_rate_id", sa.Integer(), nullable=True))
    op.add_column("product_offerings", sa.Column("iva_rate_percent", sa.Numeric(6, 3), nullable=True))
    op.create_foreign_key("fk_product_offerings_iva_rate_id", "product_offerings", "arca_iva_rates", ["iva_rate_id"], ["arca_id"], ondelete="SET NULL")
    op.create_check_constraint("ck_product_offerings_iva_rate_percent_nonnegative", "product_offerings", "iva_rate_percent IS NULL OR iva_rate_percent >= 0")

    op.add_column("invoices", sa.Column("internal_number", sa.BigInteger(), nullable=True))
    op.add_column("invoices", sa.Column("fiscal_kind", sa.String(length=20), nullable=False, server_default="internal"))
    op.add_column("invoices", sa.Column("fiscal_status", sa.String(length=30), nullable=False, server_default="draft"))
    op.add_column("invoices", sa.Column("arca_environment", sa.String(length=20), nullable=True))
    op.add_column("invoices", sa.Column("arca_cbte_tipo", sa.Integer(), nullable=True))
    op.add_column("invoices", sa.Column("arca_point_of_sale", sa.Integer(), nullable=True))
    op.add_column("invoices", sa.Column("arca_invoice_number", sa.BigInteger(), nullable=True))
    op.add_column("invoices", sa.Column("arca_cae", sa.String(length=32), nullable=True))
    op.add_column("invoices", sa.Column("arca_cae_due_date", sa.Date(), nullable=True))
    op.add_column("invoices", sa.Column("arca_authorized_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("invoices", sa.Column("arca_result", sa.String(length=20), nullable=True))
    op.add_column("invoices", sa.Column("arca_observations_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("invoices", sa.Column("arca_errors_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("invoices", sa.Column("arca_request_id", sa.BigInteger(), nullable=True))
    op.add_column("invoices", sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("invoices", sa.Column("locked_by", sa.String(length=120), nullable=True))
    op.execute("UPDATE invoices SET internal_number = invoice_number WHERE internal_number IS NULL")
    op.execute("UPDATE invoices SET fiscal_kind = CASE WHEN declared THEN 'fiscal' ELSE 'internal' END")
    op.alter_column("invoices", "internal_number", nullable=False)
    op.create_check_constraint("ck_invoices_internal_number_positive", "invoices", "internal_number > 0")
    op.create_check_constraint("ck_invoices_fiscal_kind_valid", "invoices", "fiscal_kind IN ('internal', 'fiscal')")
    op.create_check_constraint("ck_invoices_fiscal_status_valid", "invoices", "fiscal_status IN ('draft', 'pending_authorization', 'authorized', 'rejected', 'cancelled')")
    op.create_check_constraint("ck_invoices_arca_environment_valid", "invoices", "arca_environment IS NULL OR arca_environment IN ('homologation', 'production')")
    op.create_check_constraint("ck_invoices_arca_cbte_tipo_positive", "invoices", "arca_cbte_tipo IS NULL OR arca_cbte_tipo > 0")
    op.create_check_constraint("ck_invoices_arca_point_of_sale_positive", "invoices", "arca_point_of_sale IS NULL OR arca_point_of_sale > 0")
    op.create_check_constraint("ck_invoices_arca_invoice_number_positive", "invoices", "arca_invoice_number IS NULL OR arca_invoice_number > 0")
    op.create_unique_constraint("uq_invoices_internal_number", "invoices", ["internal_number"])
    op.create_unique_constraint("uq_invoices_arca_number", "invoices", ["arca_environment", "arca_cbte_tipo", "arca_point_of_sale", "arca_invoice_number"])

    op.add_column("invoice_items", sa.Column("iva_rate_id", sa.Integer(), nullable=True))
    op.add_column("invoice_items", sa.Column("iva_rate_percent", sa.Numeric(6, 3), nullable=True))
    op.add_column("invoice_items", sa.Column("net_unit_price", sa.Numeric(14, 4), nullable=True))
    op.add_column("invoice_items", sa.Column("gross_unit_price", sa.Numeric(14, 4), nullable=True))
    op.add_column("invoice_items", sa.Column("tax_amount", sa.Numeric(14, 2), nullable=True))
    op.add_column("invoice_items", sa.Column("line_net_amount", sa.Numeric(14, 2), nullable=True))
    op.add_column("invoice_items", sa.Column("line_tax_amount", sa.Numeric(14, 2), nullable=True))
    op.add_column("invoice_items", sa.Column("line_total_amount", sa.Numeric(14, 2), nullable=True))
    op.create_foreign_key("fk_invoice_items_iva_rate_id", "invoice_items", "arca_iva_rates", ["iva_rate_id"], ["arca_id"], ondelete="SET NULL")
    op.create_check_constraint("ck_invoice_items_iva_rate_percent_nonnegative", "invoice_items", "iva_rate_percent IS NULL OR iva_rate_percent >= 0")

    op.create_table(
        "invoice_tax_breakdown",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("invoice_id", sa.BigInteger(), sa.ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("arca_iva_id", sa.Integer(), sa.ForeignKey("arca_iva_rates.arca_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("iva_rate_percent", sa.Numeric(6, 3), nullable=False),
        sa.Column("base_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("tax_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("iva_rate_percent >= 0", name="ck_invoice_tax_breakdown_iva_rate_percent_nonnegative"),
        sa.CheckConstraint("base_amount >= 0", name="ck_invoice_tax_breakdown_base_amount_nonnegative"),
        sa.CheckConstraint("tax_amount >= 0", name="ck_invoice_tax_breakdown_tax_amount_nonnegative"),
        sa.UniqueConstraint("invoice_id", "arca_iva_id", name="uq_invoice_tax_breakdown_invoice_rate"),
    )

    op.create_table(
        "arca_requests",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("invoice_id", sa.BigInteger(), sa.ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True),
        sa.Column("operation", sa.String(length=60), nullable=False),
        sa.Column("environment", sa.String(length=20), nullable=False),
        sa.Column("request_xml", sa.Text(), nullable=True),
        sa.Column("response_xml", sa.Text(), nullable=True),
        sa.Column("parsed_response_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("error_code", sa.String(length=60), nullable=True),
        sa.Column("created_by", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("char_length(btrim(operation)) > 0", name="ck_arca_requests_operation_not_blank"),
        sa.CheckConstraint("environment IN ('homologation', 'production')", name="ck_arca_requests_environment_valid"),
        sa.CheckConstraint("char_length(btrim(status)) > 0", name="ck_arca_requests_status_not_blank"),
    )
    op.create_foreign_key("fk_invoices_arca_request_id", "invoices", "arca_requests", ["arca_request_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    op.drop_constraint("fk_invoices_arca_request_id", table_name="invoices", type_="foreignkey")
    op.drop_table("arca_requests")
    op.drop_table("invoice_tax_breakdown")
    op.drop_constraint("fk_invoice_items_iva_rate_id", table_name="invoice_items", type_="foreignkey")
    for column_name in [
        "line_total_amount",
        "line_tax_amount",
        "line_net_amount",
        "tax_amount",
        "gross_unit_price",
        "net_unit_price",
        "iva_rate_percent",
        "iva_rate_id",
    ]:
        op.drop_column("invoice_items", column_name)
    op.drop_constraint("uq_invoices_arca_number", table_name="invoices", type_="unique")
    op.drop_constraint("uq_invoices_internal_number", table_name="invoices", type_="unique")
    for constraint_name in [
        "ck_invoices_arca_invoice_number_positive",
        "ck_invoices_arca_point_of_sale_positive",
        "ck_invoices_arca_cbte_tipo_positive",
        "ck_invoices_arca_environment_valid",
        "ck_invoices_fiscal_status_valid",
        "ck_invoices_fiscal_kind_valid",
        "ck_invoices_internal_number_positive",
    ]:
        op.drop_constraint(constraint_name, table_name="invoices", type_="check")
    for column_name in [
        "locked_by",
        "locked_at",
        "arca_request_id",
        "arca_errors_json",
        "arca_observations_json",
        "arca_result",
        "arca_authorized_at",
        "arca_cae_due_date",
        "arca_cae",
        "arca_invoice_number",
        "arca_point_of_sale",
        "arca_cbte_tipo",
        "arca_environment",
        "fiscal_status",
        "fiscal_kind",
        "internal_number",
    ]:
        op.drop_column("invoices", column_name)
    op.drop_constraint("fk_product_offerings_iva_rate_id", table_name="product_offerings", type_="foreignkey")
    op.drop_constraint("ck_product_offerings_iva_rate_percent_nonnegative", table_name="product_offerings", type_="check")
    op.drop_column("product_offerings", "iva_rate_percent")
    op.drop_column("product_offerings", "iva_rate_id")
    op.drop_table("arca_iva_rates")

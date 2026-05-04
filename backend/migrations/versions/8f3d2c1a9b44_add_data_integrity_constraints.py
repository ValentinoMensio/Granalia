"""Add database data integrity constraints.

Revision ID: 8f3d2c1a9b44
Revises: 6a4c2b9a7f11
Create Date: 2026-04-26 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "8f3d2c1a9b44"
down_revision: Union[str, Sequence[str], None] = "6a4c2b9a7f11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CONSTRAINTS: list[tuple[str, str, str]] = [
    ("catalogs", "ck_catalogs_name_not_blank", "char_length(btrim(name)) > 0"),
    ("catalogs", "ck_catalogs_source_not_blank", "char_length(btrim(source)) > 0"),
    ("catalogs", "ck_catalogs_catalog_array", "jsonb_typeof(catalog) = 'array'"),
    ("price_lists", "ck_price_lists_filename_not_blank", "char_length(btrim(filename)) > 0"),
    ("price_lists", "ck_price_lists_content_type_not_blank", "char_length(btrim(content_type)) > 0"),
    ("price_lists", "ck_price_lists_source_not_blank", "char_length(btrim(source)) > 0"),
    ("price_lists", "ck_price_lists_size_range", "size > 0 AND size <= 20971520"),
    ("price_lists", "ck_price_lists_pdf_size_matches", "octet_length(pdf_data) = size"),
    ("transports", "ck_transports_name_not_blank", "char_length(btrim(name)) > 0"),
    ("transports", "ck_transports_notes_array", "jsonb_typeof(notes) = 'array'"),
    (
        "transports",
        "ck_transports_notes_max_items",
        "CASE WHEN jsonb_typeof(notes) = 'array' THEN jsonb_array_length(notes) <= 30 ELSE false END",
    ),
    ("customers", "ck_customers_name_not_blank", "char_length(btrim(name)) > 0"),
    ("customers", "ck_customers_secondary_line_max_length", "char_length(secondary_line) <= 500"),
    ("customers", "ck_customers_notes_array", "jsonb_typeof(notes) = 'array'"),
    (
        "customers",
        "ck_customers_notes_max_items",
        "CASE WHEN jsonb_typeof(notes) = 'array' THEN jsonb_array_length(notes) <= 30 ELSE false END",
    ),
    ("customers", "ck_customers_footer_discounts_array", "jsonb_typeof(footer_discounts) = 'array'"),
    (
        "customers",
        "ck_customers_footer_discounts_max_items",
        "CASE WHEN jsonb_typeof(footer_discounts) = 'array' THEN jsonb_array_length(footer_discounts) <= 30 ELSE false END",
    ),
    ("customers", "ck_customers_line_discounts_object", "jsonb_typeof(line_discounts_by_format) = 'object'"),
    ("customers", "ck_customers_source_count_nonnegative", "source_count >= 0"),
    ("products", "ck_products_name_not_blank", "char_length(btrim(name)) > 0"),
    ("products", "ck_products_aliases_array", "jsonb_typeof(aliases) = 'array'"),
    (
        "products",
        "ck_products_aliases_max_items",
        "CASE WHEN jsonb_typeof(aliases) = 'array' THEN jsonb_array_length(aliases) <= 50 ELSE false END",
    ),
    ("product_offerings", "ck_product_offerings_label_not_blank", "char_length(btrim(label)) > 0"),
    ("product_offerings", "ck_product_offerings_price_nonnegative", "price >= 0"),
    ("product_offerings", "ck_product_offerings_position_positive", "position > 0"),
    ("invoices", "ck_invoices_legacy_key_not_blank", "legacy_key IS NULL OR char_length(btrim(legacy_key)) > 0"),
    ("invoices", "ck_invoices_client_name_not_blank", "char_length(btrim(client_name)) > 0"),
    ("invoices", "ck_invoices_secondary_line_max_length", "char_length(secondary_line) <= 500"),
    ("invoices", "ck_invoices_transport_max_length", "char_length(transport) <= 500"),
    ("invoices", "ck_invoices_notes_array", "jsonb_typeof(notes) = 'array'"),
    (
        "invoices",
        "ck_invoices_notes_max_items",
        "CASE WHEN jsonb_typeof(notes) = 'array' THEN jsonb_array_length(notes) <= 30 ELSE false END",
    ),
    ("invoices", "ck_invoices_footer_discounts_array", "jsonb_typeof(footer_discounts) = 'array'"),
    (
        "invoices",
        "ck_invoices_footer_discounts_max_items",
        "CASE WHEN jsonb_typeof(footer_discounts) = 'array' THEN jsonb_array_length(footer_discounts) <= 30 ELSE false END",
    ),
    ("invoices", "ck_invoices_line_discounts_object", "jsonb_typeof(line_discounts_by_format) = 'object'"),
    ("invoices", "ck_invoices_total_bultos_nonnegative", "total_bultos >= 0"),
    ("invoices", "ck_invoices_gross_total_nonnegative", "gross_total >= 0"),
    ("invoices", "ck_invoices_discount_total_nonnegative", "discount_total >= 0"),
    ("invoices", "ck_invoices_final_total_nonnegative", "final_total >= 0"),
    ("invoices", "ck_invoices_discount_not_above_gross", "discount_total <= gross_total"),
    ("invoices", "ck_invoices_output_filename_not_blank", "char_length(btrim(output_filename)) > 0"),
    ("invoices", "ck_invoices_xlsx_size_positive", "xlsx_size > 0"),
    ("invoices", "ck_invoices_xlsx_size_matches", "octet_length(xlsx_data) = xlsx_size"),
    ("invoice_items", "ck_invoice_items_line_number_positive", "line_number > 0"),
    ("invoice_items", "ck_invoice_items_label_not_blank", "char_length(btrim(label)) > 0"),
    ("invoice_items", "ck_invoice_items_quantity_nonnegative", "quantity >= 0"),
    ("invoice_items", "ck_invoice_items_unit_price_nonnegative", "unit_price >= 0"),
    ("invoice_items", "ck_invoice_items_gross_nonnegative", "gross >= 0"),
    ("invoice_items", "ck_invoice_items_discount_nonnegative", "discount >= 0"),
    ("invoice_items", "ck_invoice_items_total_nonnegative", "total >= 0"),
    ("invoice_items", "ck_invoice_items_discount_not_above_gross", "discount <= gross"),
    ("app_users", "ck_app_users_username_not_blank", "char_length(btrim(username)) > 0"),
    ("app_users", "ck_app_users_password_hash_not_blank", "char_length(btrim(password_hash)) > 0"),
]


def upgrade() -> None:
    for table_name, constraint_name, condition in CONSTRAINTS:
        op.create_check_constraint(constraint_name, table_name, condition)


def downgrade() -> None:
    for table_name, constraint_name, _condition in reversed(CONSTRAINTS):
        op.drop_constraint(constraint_name, table_name=table_name, type_="check")

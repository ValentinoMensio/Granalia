import os
from pathlib import Path
from sqlalchemy import select
from app.core.utils import discount_key_for_label
from app.infrastructure.postgres import PostgresRepository

def debug_formats():
    repo = PostgresRepository(Path("."))
    with repo.engine.connect() as conn:
        # 1. Check ALL product offering formats
        print("--- PRODUCT OFFERING FORMATS ---")
        res = conn.execute(select(repo.product_offerings.c.label).distinct()).all()
        formats = [discount_key_for_label(r[0]) for r in res if r[0]]
        print(f"Unique formats: {formats}")

        # 2. Check Agazzi's discounts
        print("\n--- AGAZZI DISCOUNTS ---")
        row = conn.execute(
            select(repo.customers.c.line_discounts_by_format)
            .where(repo.customers.c.name == 'Agazzi, Gustavo')
        ).mappings().first()
        if row:
            print(f"Discounts: {row['line_discounts_by_format']}")
        else:
            print("Customer not found")

if __name__ == "__main__":
    if not os.getenv("GRANALIA_POSTGRES_URL"):
        os.environ["GRANALIA_POSTGRES_URL"] = "postgresql+psycopg://granalia:granalia@127.0.0.1:5432/granalia"
    debug_formats()

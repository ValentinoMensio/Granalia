import os
from pathlib import Path
from sqlalchemy import select
from app.core.utils import discount_key_for_label
from app.infrastructure.postgres import PostgresRepository

def verify_everything():
    repo = PostgresRepository(Path("."))
    with repo.engine.connect() as conn:
        # 1. Offerings
        print("--- OFFERINGS ---")
        res = conn.execute(select(repo.product_offerings.c.label).distinct()).all()
        print(f"Formats: {[discount_key_for_label(r[0]) for r in res]}")

        # 2. Agazzi
        print("\n--- AGAZZI ---")
        row = conn.execute(
            select(repo.customers.c.line_discounts_by_format)
            .where(repo.customers.c.name == 'Agazzi, Gustavo')
        ).mappings().first()
        print(f"Discounts: {row['line_discounts_by_format'] if row else 'Not found'}")

        # 3. Catalogs
        print("\n--- CATALOGS ---")
        cats = conn.execute(select(repo.catalogs.c.catalog)).all()
        for c in cats:
            # Just check first product of first catalog
            if c[0] and len(c[0]) > 0:
                p = c[0][0]
                if "offerings" in p and len(p["offerings"]) > 0:
                    print(f"Catalog format sample: {p['offerings'][0].get('format_class')}")

if __name__ == "__main__":
    if not os.getenv("GRANALIA_POSTGRES_URL"):
        os.environ["GRANALIA_POSTGRES_URL"] = "postgresql+psycopg://granalia:granalia@127.0.0.1:5432/granalia"
    verify_everything()

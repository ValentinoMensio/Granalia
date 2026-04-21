import os
from pathlib import Path
from sqlalchemy import select
from app.infrastructure.postgres import PostgresRepository

def check_all_avena():
    repo = PostgresRepository(Path("."))
    with repo.engine.connect() as conn:
        stmt = select(repo.products.c.product_id, repo.products.c.name)
        products = conn.execute(stmt).mappings().all()
        
        avena_products = [p for p in products if "avena" in p["name"].lower()]
        
        for p in avena_products:
            print(f"Product: {p['name']} (ID: {p['product_id']})")
            offering_stmt = select(repo.product_offerings).where(repo.product_offerings.c.product_id == p['product_id'])
            offerings = conn.execute(offering_stmt).mappings().all()
            for o in offerings:
                print(f"  Offering: {o['label']} | Format: {o['format_class']} | Price: {o['price']}")

if __name__ == "__main__":
    if not os.getenv("GRANALIA_POSTGRES_URL"):
        os.environ["GRANALIA_POSTGRES_URL"] = "postgresql+psycopg://granalia:granalia@127.0.0.1:5432/granalia"
    check_all_avena()

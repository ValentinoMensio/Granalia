import os
import copy
from pathlib import Path
from sqlalchemy import update, select
from app.infrastructure.postgres import PostgresRepository

def migrate_catalog_snapshots():
    repo = PostgresRepository(Path("."))
    
    mapping = {
        "bag4": "Bolsa 4kg",
        "bag4%": "Bolsa 4kg",
        "bag5": "Bolsa 5kg",
        "bulk25": "Granel 25kg",
        "bulk30": "Granel 30kg",
        "pack10_1000": "Pack 10 x 1kg",
        "pack10_500": "Pack 10 x 500g",
        "pack12": "Pack 12",
    }

    def translate_catalog(catalog_data):
        # Use deepcopy to avoid modifying the original object in place
        new_catalog = copy.deepcopy(catalog_data)
        if not isinstance(new_catalog, list):
            return new_catalog
            
        changed = False
        for product in new_catalog:
            if "offerings" in product:
                for offering in product["offerings"]:
                    fmt = offering.get("format_class", "")
                    if not fmt: continue
                    
                    new_name = fmt
                    if fmt in mapping:
                        new_name = mapping[fmt]
                    else:
                        # Flexible match
                        for k, v in mapping.items():
                            if k in fmt.lower():
                                new_name = v
                                break
                    
                    if new_name != fmt:
                        offering["format_class"] = new_name
                        changed = True
        return new_catalog, changed

    with repo.engine.begin() as conn:
        print("Migrando snapshots de la tabla 'catalogs'...")
        catalogs = conn.execute(select(repo.catalogs)).mappings().all()
        
        updated_count = 0
        for cat in catalogs:
            original_json = cat["catalog"]
            updated_json, was_changed = translate_catalog(original_json)
            
            if was_changed:
                conn.execute(
                    update(repo.catalogs)
                    .where(repo.catalogs.c.id == cat["id"])
                    .values(catalog=updated_json)
                )
                print(f"  Catálogo {cat['id']} ({cat['name']}) actualizado")
                updated_count += 1

    print(f"\nMigración de snapshots completada. {updated_count} catálogos actualizados.")

if __name__ == "__main__":
    if not os.getenv("GRANALIA_POSTGRES_URL"):
        os.environ["GRANALIA_POSTGRES_URL"] = "postgresql+psycopg://granalia:granalia@127.0.0.1:5432/granalia"
    migrate_catalog_snapshots()

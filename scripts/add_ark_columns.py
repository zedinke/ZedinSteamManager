#!/usr/bin/env python3
"""
Migration script - Ark oszlopok hozzáadása a server_instances táblához
"""

import sys
from pathlib import Path

# Projekt gyökér hozzáadása a Python path-hoz
BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.database import engine, SessionLocal
from sqlalchemy import inspect, text

def add_ark_columns():
    """Ark oszlopok hozzáadása a server_instances táblához"""
    print("Ark oszlopok hozzáadása a server_instances táblához...")
    
    inspector = inspect(engine)
    
    if 'server_instances' not in inspector.get_table_names():
        print("✗ server_instances tábla nem található!")
        return False
    
    existing_columns = [col['name'] for col in inspector.get_columns('server_instances')]
    print(f"Létező oszlopok: {', '.join(existing_columns)}")
    
    # ID típus lekérése
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT COLUMN_TYPE 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_SCHEMA = DATABASE() 
            AND TABLE_NAME = 'users' 
            AND COLUMN_NAME = 'id'
        """))
        row = result.fetchone()
        id_type = row[0] if row else "INT(11) UNSIGNED"
    
    columns_to_add = {
        'cluster_id': f'{id_type} NULL',
        'max_players': 'INT NOT NULL DEFAULT 40',
        'query_port': 'INT NULL',
        'active_mods': 'JSON NULL',
        'passive_mods': 'JSON NULL',
        'server_path': 'VARCHAR(500) NULL'
    }
    
    success_count = 0
    error_count = 0
    
    for col_name, col_def in columns_to_add.items():
        if col_name not in existing_columns:
            print(f"\n{col_name} oszlop hozzáadása...")
            try:
                with engine.connect() as conn:
                    conn.execute(text(f"""
                        ALTER TABLE server_instances 
                        ADD COLUMN {col_name} {col_def}
                    """))
                    conn.commit()
                    
                    # Index hozzáadása cluster_id-hez
                    if col_name == 'cluster_id':
                        try:
                            conn.execute(text("""
                                ALTER TABLE server_instances 
                                ADD INDEX ix_server_instances_cluster_id (cluster_id)
                            """))
                            conn.commit()
                        except Exception as e:
                            if "duplicate key name" not in str(e).lower():
                                print(f"    Figyelmeztetés: index: {e}")
                    
                    print(f"✓ {col_name} oszlop hozzáadva")
                    success_count += 1
            except Exception as e:
                error_str = str(e).lower()
                if "duplicate column name" not in error_str:
                    print(f"✗ Hiba {col_name} oszlop hozzáadásakor: {e}")
                    error_count += 1
                else:
                    print(f"  {col_name} oszlop már létezik")
        else:
            print(f"  {col_name} oszlop már létezik")
    
    # Foreign key hozzáadása cluster_id-hez (ha létezik a clusters tábla)
    if 'cluster_id' in existing_columns or 'cluster_id' in [c for c in columns_to_add.keys()]:
        existing_tables = inspector.get_table_names()
        if 'clusters' in existing_tables:
            print("\nForeign key hozzáadása cluster_id-hez...")
            try:
                with engine.connect() as conn:
                    # Ellenőrizzük, hogy létezik-e már a foreign key
                    result = conn.execute(text("""
                        SELECT CONSTRAINT_NAME 
                        FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE 
                        WHERE TABLE_SCHEMA = DATABASE() 
                        AND TABLE_NAME = 'server_instances' 
                        AND CONSTRAINT_NAME = 'fk_server_instances_cluster_id'
                    """))
                    if not result.fetchone():
                        conn.execute(text("""
                            ALTER TABLE server_instances 
                            ADD CONSTRAINT fk_server_instances_cluster_id
                            FOREIGN KEY (cluster_id) REFERENCES clusters(id) ON DELETE SET NULL
                        """))
                        conn.commit()
                        print("✓ Foreign key hozzáadva")
                    else:
                        print("  Foreign key már létezik")
            except Exception as e:
                error_str = str(e).lower()
                if "duplicate foreign key" not in error_str and "already exists" not in error_str:
                    print(f"  Figyelmeztetés: foreign key: {e}")
    
    print(f"\n✓ Kész! {success_count} oszlop hozzáadva, {error_count} hiba")
    return error_count == 0

if __name__ == "__main__":
    try:
        success = add_ark_columns()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"✗ Hiba: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


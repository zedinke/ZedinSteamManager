"""
Script a tokens tábla generated_by oszlop javításához
"""

from app.database import engine
from sqlalchemy import inspect, text

def fix_tokens_table():
    """Javítja a tokens tábla generated_by/generated_by_id oszlopát"""
    inspector = inspect(engine)
    
    if 'tokens' not in inspector.get_table_names():
        print("✗ A tokens tábla nem létezik!")
        return
    
    columns = [col['name'] for col in inspector.get_columns('tokens')]
    print(f"Tokens tábla oszlopok: {columns}")
    
    has_generated_by = 'generated_by' in columns
    has_generated_by_id = 'generated_by_id' in columns
    
    with engine.connect() as conn:
        if has_generated_by and not has_generated_by_id:
            # Átnevezzük generated_by_id-re
            print("generated_by oszlop átnevezése generated_by_id-re...")
            try:
                conn.execute(text("""
                    ALTER TABLE tokens 
                    CHANGE COLUMN generated_by generated_by_id INT(11) UNSIGNED NOT NULL
                """))
                conn.commit()
                print("✓ Átnevezve generated_by_id-re")
            except Exception as e:
                print(f"✗ Hiba az átnevezéskor: {e}")
                # Próbáljuk meg úgy, hogy először NULL-ra állítjuk
                try:
                    conn.execute(text("""
                        ALTER TABLE tokens 
                        MODIFY COLUMN generated_by INT(11) UNSIGNED NULL
                    """))
                    conn.commit()
                    
                    # Kitöltjük a meglévő rekordokat
                    conn.execute(text("""
                        UPDATE tokens 
                        SET generated_by = (SELECT id FROM users WHERE role = 'manager_admin' LIMIT 1)
                        WHERE generated_by IS NULL
                    """))
                    conn.commit()
                    
                    # Most átnevezzük
                    conn.execute(text("""
                        ALTER TABLE tokens 
                        CHANGE COLUMN generated_by generated_by_id INT(11) UNSIGNED NOT NULL
                    """))
                    conn.commit()
                    print("✓ Átnevezve generated_by_id-re (NULL értékek kitöltve)")
                except Exception as e2:
                    print(f"✗ Hiba: {e2}")
                    return
        
        elif not has_generated_by_id:
            # Hozzáadjuk a generated_by_id oszlopot
            print("generated_by_id oszlop hozzáadása...")
            try:
                # Először NULL-ként
                conn.execute(text("""
                    ALTER TABLE tokens 
                    ADD COLUMN generated_by_id INT(11) UNSIGNED NULL
                """))
                conn.commit()
                
                # Kitöltjük a meglévő rekordokat
                conn.execute(text("""
                    UPDATE tokens 
                    SET generated_by_id = (SELECT id FROM users WHERE role = 'manager_admin' LIMIT 1)
                    WHERE generated_by_id IS NULL
                """))
                conn.commit()
                
                # NOT NULL-ra állítjuk
                conn.execute(text("""
                    ALTER TABLE tokens 
                    MODIFY COLUMN generated_by_id INT(11) UNSIGNED NOT NULL
                """))
                conn.commit()
                print("✓ generated_by_id oszlop hozzáadva")
            except Exception as e:
                print(f"✗ Hiba: {e}")
                return
        
        # Foreign key ellenőrzése
        try:
            # Ellenőrizzük, hogy van-e foreign key
            fks = inspector.get_foreign_keys('tokens')
            has_fk = any(fk['name'] == 'fk_tokens_generated_by' or 
                        (fk['constrained_columns'] == ['generated_by_id'] and 
                         fk['referred_table'] == 'users') 
                        for fk in fks)
            
            if not has_fk:
                print("Foreign key hozzáadása...")
                conn.execute(text("""
                    ALTER TABLE tokens 
                    ADD CONSTRAINT fk_tokens_generated_by 
                    FOREIGN KEY (generated_by_id) REFERENCES users(id) ON DELETE CASCADE
                """))
                conn.commit()
                print("✓ Foreign key hozzáadva")
        except Exception as e:
            if "Duplicate foreign key" not in str(e) and "already exists" not in str(e).lower():
                print(f"  Figyelmeztetés: Foreign key: {e}")
        
        # Index ellenőrzése
        try:
            indexes = [idx['name'] for idx in inspector.get_indexes('tokens')]
            if 'ix_tokens_generated_by_id' not in indexes:
                print("Index hozzáadása...")
                conn.execute(text("""
                    ALTER TABLE tokens 
                    ADD INDEX ix_tokens_generated_by_id (generated_by_id)
                """))
                conn.commit()
                print("✓ Index hozzáadva")
        except Exception as e:
            if "Duplicate key name" not in str(e):
                print(f"  Figyelmeztetés: Index: {e}")
    
    print("\n✓ Kész! A tokens tábla javítva.")

if __name__ == "__main__":
    print("Tokens tábla javítása\n")
    fix_tokens_table()


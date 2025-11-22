"""
Adatbázis inicializálás
"""

from app.database import Base, engine, SessionLocal, User, UserRole
from app.services.auth_service import get_password_hash
from app.config import settings

def init_db():
    """Adatbázis táblák létrehozása"""
    print("Adatbázis táblák létrehozása...")
    try:
        Base.metadata.create_all(bind=engine)
        print("✓ Táblák létrehozva")
        
        # Ellenőrzés és hiányzó oszlopok hozzáadása
        from sqlalchemy import inspect, text
        inspector = inspect(engine)
        
        # Users tábla ellenőrzése
        if 'users' in inspector.get_table_names():
            columns = [col['name'] for col in inspector.get_columns('users')]
            indexes = [idx['name'] for idx in inspector.get_indexes('users')]
            
            # created_by_id oszlop hozzáadása ha hiányzik
            if 'created_by_id' not in columns:
                print("created_by_id oszlop hozzáadása a users táblához...")
                with engine.connect() as conn:
                    # Először az oszlop
                    conn.execute(text("""
                        ALTER TABLE users 
                        ADD COLUMN created_by_id INT(11) UNSIGNED NULL
                    """))
                    conn.commit()
                    
                    # Aztán az index, ha még nincs
                    if 'idx_created_by' not in indexes:
                        conn.execute(text("""
                            ALTER TABLE users 
                            ADD INDEX idx_created_by (created_by_id)
                        """))
                        conn.commit()
                print("✓ created_by_id oszlop hozzáadva")
        
    except Exception as e:
        print(f"✗ Hiba a táblák létrehozásakor: {e}")
        raise

def create_default_admin():
    """Alapértelmezett Manager Admin létrehozása"""
    db = SessionLocal()
    try:
        # Ellenőrzés: van-e már Manager Admin
        existing = db.query(User).filter(User.role == UserRole.MANAGER_ADMIN).first()
        if existing:
            print("✓ Manager Admin már létezik")
            return
        
        # Alapértelmezett admin létrehozása
        admin = User(
            username="admin",
            email="admin@example.com",
            password_hash=get_password_hash("admin123"),
            role=UserRole.MANAGER_ADMIN,
            email_verified=True
        )
        
        db.add(admin)
        db.commit()
        print("✓ Alapértelmezett Manager Admin létrehozva")
        print("  Email: admin@example.com")
        print("  Jelszó: admin123")
        print("  ⚠️  FONTOS: Változtasd meg az első bejelentkezés után!")
    except Exception as e:
        print(f"✗ Hiba: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    print("ZedinArkManager - Adatbázis inicializálás\n")
    init_db()
    create_default_admin()
    print("\n✓ Kész!")


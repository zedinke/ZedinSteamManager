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


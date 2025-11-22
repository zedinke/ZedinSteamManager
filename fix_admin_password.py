#!/usr/bin/env python3
"""
Admin jelszó javító script - újra hash-elés
"""

import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from app.database import SessionLocal, User, UserRole
from app.services.auth_service import get_password_hash

def fix_admin_password():
    """Admin jelszó újra hash-elése"""
    db = SessionLocal()
    try:
        admin = db.query(User).filter(
            User.email == "admin@example.com",
            User.role == UserRole.MANAGER_ADMIN
        ).first()
        
        if admin:
            print(f"Jelenlegi password_hash: {admin.password_hash[:50]}...")
            print("Új password hash generálása...")
            
            # Új hash generálása
            new_hash = get_password_hash("admin123")
            admin.password_hash = new_hash
            db.commit()
            
            print("✓ Admin jelszó hash frissítve")
            print(f"Új hash: {new_hash[:50]}...")
        else:
            print("Admin felhasználó nem található")
    except Exception as e:
        print(f"✗ Hiba: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    print("Admin jelszó javítás\n")
    fix_admin_password()
    print("\n✓ Kész!")


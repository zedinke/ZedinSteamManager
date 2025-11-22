#!/usr/bin/env python3
"""
Token lejárat ellenőrző cron job
"""

import sys
from pathlib import Path

# Projekt gyökér hozzáadása a path-hoz
BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.database import SessionLocal
from app.services.token_service import check_expiring_tokens
import asyncio

def main():
    """Token lejárat ellenőrzés"""
    db = SessionLocal()
    try:
        count = asyncio.run(check_expiring_tokens(db))
        print(f"Token lejárat ellenőrzés befejezve. {count} értesítés küldve.")
    except Exception as e:
        print(f"Hiba történt: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    main()


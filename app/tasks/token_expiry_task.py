"""
Token lejárat kezelés - háttérben futó task
"""

import asyncio
import logging
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.services.token_expiry_service import process_expired_tokens, cleanup_expired_servers

logger = logging.getLogger(__name__)

async def run_token_expiry_check():
    """Token lejárat ellenőrzés futtatása"""
    db = SessionLocal()
    try:
        expired_count = process_expired_tokens(db)
        if expired_count > 0:
            logger.info(f"{expired_count} lejárt token feldolgozva")
        
        deleted_count = cleanup_expired_servers(db)
        if deleted_count > 0:
            logger.info(f"{deleted_count} szerver törölve (grace period lejárt)")
    except Exception as e:
        logger.error(f"Hiba a token lejárat ellenőrzés során: {e}")
    finally:
        db.close()

async def token_expiry_worker():
    """Token lejárat worker - óránként fut"""
    while True:
        try:
            await run_token_expiry_check()
        except Exception as e:
            logger.error(f"Hiba a token expiry worker-ben: {e}")
        
        # Várunk 1 órát
        await asyncio.sleep(3600)  # 3600 másodperc = 1 óra


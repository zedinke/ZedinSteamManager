#!/usr/bin/env python3
"""
Lejárt tokenekkel rendelkező szerverek automatikus leállítása
"""

import sys
from pathlib import Path
from datetime import datetime

# Projekt gyökér hozzáadása a path-hoz
BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.database import SessionLocal, ServerInstance, Token, ServerStatus
from app.services.server_control_service import stop_server
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """Lejárt tokenekkel rendelkező szerverek leállítása"""
    db = SessionLocal()
    try:
        # Keresünk olyan szervereket, amelyeknek lejárt a tokenje és még futnak
        now = datetime.utcnow()
        
        # Szerverek, amelyeknek lejárt a token_expires_at
        expired_servers = db.query(ServerInstance).filter(
            ServerInstance.token_expires_at.isnot(None),
            ServerInstance.token_expires_at <= now,
            ServerInstance.status.in_([ServerStatus.RUNNING, ServerStatus.STARTING])
        ).all()
        
        # Szerverek, amelyeknek a token_used_id-hoz tartozó token lejárt vagy inaktív
        servers_with_invalid_tokens = db.query(ServerInstance).join(
            Token, ServerInstance.token_used_id == Token.id
        ).filter(
            ServerInstance.token_used_id.isnot(None),
            ServerInstance.status.in_([ServerStatus.RUNNING, ServerStatus.STARTING]),
            (
                (Token.is_active == False) |
                (Token.expires_at <= now)
            )
        ).all()
        
        # Szerverek, amelyeknek nincs token_used_id, de még futnak
        servers_without_tokens = db.query(ServerInstance).filter(
            ServerInstance.token_used_id.is_(None),
            ServerInstance.status.in_([ServerStatus.RUNNING, ServerStatus.STARTING])
        ).all()
        
        # Összegyűjtjük az összes leállítandó szervert (duplikációk nélkül)
        servers_to_stop = {}
        for server in expired_servers:
            servers_to_stop[server.id] = server
        for server in servers_with_invalid_tokens:
            servers_to_stop[server.id] = server
        for server in servers_without_tokens:
            servers_to_stop[server.id] = server
        
        if not servers_to_stop:
            logger.info("Nincs leállítandó szerver lejárt token miatt.")
            return
        
        logger.info(f"{len(servers_to_stop)} szerver leállítása lejárt token miatt...")
        
        stopped_count = 0
        error_count = 0
        
        for server_id, server in servers_to_stop.items():
            try:
                logger.info(f"Szerver {server_id} ({server.name}) leállítása - token lejárt vagy hiányzik")
                result = stop_server(server, db)
                
                if result["success"]:
                    stopped_count += 1
                    logger.info(f"Szerver {server_id} sikeresen leállítva")
                else:
                    error_count += 1
                    logger.error(f"Szerver {server_id} leállítása sikertelen: {result.get('message', 'Ismeretlen hiba')}")
            except Exception as e:
                error_count += 1
                logger.error(f"Hiba a szerver {server_id} leállítása során: {e}", exc_info=True)
        
        logger.info(f"Leállítás befejezve: {stopped_count} sikeres, {error_count} hiba")
        
    except Exception as e:
        logger.error(f"Hiba történt: {e}", exc_info=True)
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    main()


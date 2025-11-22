"""
Token lejárat kezelés - automatikus szerver leállítás és token inaktiválás
"""

from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.database import Token, ServerInstance, ServerStatus
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

def process_expired_tokens(db: Session):
    """
    Feldolgozza a lejárt tokeneket:
    - Legrégebbi tokenhez tartozó szerver leállítása
    - Token inaktiválása
    - 30 napos grace period beállítása
    """
    now = datetime.now()
    
    # Lejárt, de még aktív tokenek
    expired_tokens = db.query(Token).filter(
        and_(
            Token.is_active == True,
            Token.expires_at <= now
        )
    ).order_by(Token.created_at).all()
    
    for token in expired_tokens:
        # Legrégebbi szerver, ami ezt a tokent használja
        server = db.query(ServerInstance).filter(
            and_(
                ServerInstance.token_used_id == token.id,
                ServerInstance.scheduled_deletion_date.is_(None)  # Még nem ütemezett törlésre
            )
        ).order_by(ServerInstance.created_at).first()
        
        if server:
            # Szerver leállítása
            server.status = ServerStatus.STOPPED
            server.stopped_at = now
            
            # 30 napos grace period beállítása
            server.scheduled_deletion_date = now + timedelta(days=30)
            
            logger.info(f"Token {token.id} lejárt, szerver {server.id} leállítva, 30 napos grace period beállítva")
        
        # Token inaktiválása
        token.is_active = False
        logger.info(f"Token {token.id} inaktiválva (lejárat)")
    
    db.commit()
    
    return len(expired_tokens)

def cleanup_expired_servers(db: Session):
    """
    Törli a 30 napos grace period után lévő szervereket
    """
    now = datetime.now()
    
    # Szerverek, amik törlésre ütemezve vannak és lejárt a grace period
    expired_servers = db.query(ServerInstance).filter(
        and_(
            ServerInstance.scheduled_deletion_date.isnot(None),
            ServerInstance.scheduled_deletion_date <= now
        )
    ).all()
    
    count = len(expired_servers)
    
    for server in expired_servers:
        db.delete(server)
        logger.info(f"Szerver {server.id} törölve (30 napos grace period lejárt)")
    
    db.commit()
    
    return count


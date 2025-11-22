"""
Token szolgáltatás
"""

from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from app.database import Token, User, TokenType, UserRole
from app.config import settings
import secrets
from app.services.email_service import send_token_notification

def generate_token(
    db: Session,
    generated_by_id: int,
    token_type: TokenType,
    expires_in_days: int | None = None
) -> Token:
    """Token generálása"""
    if expires_in_days is None:
        expires_in_days = settings.token_expiry_days
    
    token_string = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(days=expires_in_days)
    
    token = Token(
        token=token_string,
        token_type=token_type,
        generated_by_id=generated_by_id,
        expires_at=expires_at
    )
    
    db.add(token)
    db.commit()
    db.refresh(token)
    
    return token

async def activate_token(db: Session, token_string: str, user_id: int) -> dict:
    """Token aktiválása"""
    token = db.query(Token).filter(
        Token.token == token_string,
        Token.is_active == False,
        Token.expires_at > datetime.utcnow()
    ).first()
    
    if not token:
        return {"success": False, "message": "Érvénytelen vagy lejárt token"}
    
    # Token aktiválása
    token.user_id = user_id
    token.is_active = True
    token.activated_at = datetime.utcnow()
    
    # Ha user token, akkor server_admin jogosultságot ad
    if token.token_type == TokenType.USER:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.role = UserRole.SERVER_ADMIN
    
    db.commit()
    
    return {"success": True, "token_type": token.token_type.value}

async def send_token_to_user(db: Session, token: Token, user_id: int) -> bool:
    """Token küldése email-ben és értesítésben"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return False
    
    # Email küldése
    email_sent = await send_token_notification(
        user.email,
        user.username,
        token.token,
        token.token_type.value,
        token.expires_at.strftime("%Y-%m-%d %H:%M:%S")
    )
    
    # Értesítés létrehozása a tokennel (mindig létrejön, még ha az email nem sikerült)
    from app.services.notification_service import create_notification
    type_text = "Szerver Admin" if token.token_type == TokenType.SERVER_ADMIN else "Felhasználó"
    activation_link = f"{settings.base_url}/tokens/activate?token={token.token}"
    create_notification(
        db,
        user_id,
        "token_generated",
        "Új token generálva",
        f"Ön számára egy új {type_text} token lett generálva.\n\nToken: {token.token}\nLejárat: {token.expires_at.strftime('%Y-%m-%d %H:%M:%S')}\n\nAktiválás: {activation_link}"
    )
    
    return email_sent

async def check_expiring_tokens(db: Session) -> int:
    """Lejáró tokenek ellenőrzése és értesítés küldése"""
    from app.services.notification_service import create_notification
    from app.services.email_service import send_token_expiry_warning
    
    days_before = settings.notification_days_before_expiry
    expiry_date = datetime.utcnow() + timedelta(days=days_before)
    
    tokens = db.query(Token).join(User).filter(
        Token.is_active == True,
        Token.expires_at <= expiry_date,
        Token.expires_at > datetime.utcnow()
    ).all()
    
    count = 0
    for token in tokens:
        days_left = (token.expires_at - datetime.utcnow()).days
        
        # Email küldése
        await send_token_expiry_warning(
            token.user.email,
            token.user.username,
            token.token,
            days_left
        )
        
        # Értesítés létrehozása
        create_notification(
            db,
            token.user_id,
            "token_expiry_warning",
            "Token lejárat figyelmeztetés",
            f"Tokenje {days_left} nap múlva lejár! Lejárat: {token.expires_at.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        count += 1
    
    return count


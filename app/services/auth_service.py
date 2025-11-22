"""
Autentikációs szolgáltatás
"""

from sqlalchemy.orm import Session
from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta
from app.database import User, UserRole
from app.config import settings

# Bcrypt context inicializálás explicit backend-del
try:
    pwd_context = CryptContext(
        schemes=["bcrypt"],
        deprecated="auto",
        bcrypt__ident="2b"  # Explicit bcrypt ident
    )
except Exception:
    # Ha nem sikerül, próbáljuk meg egyszerűbben
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Jelszó ellenőrzése"""
    if not hashed_password or not plain_password:
        return False
    
    # Bcrypt 72 bájt limit kezelése
    password_bytes = plain_password.encode('utf-8')
    if len(password_bytes) > 72:
        plain_password = password_bytes[:72].decode('utf-8', errors='ignore')
    
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except (ValueError, TypeError) as e:
        # Ha a hash formátuma nem megfelelő, próbáljuk meg újra hash-elni
        print(f"Password verification error: {e}")
        return False

def get_password_hash(password: str) -> str:
    """Jelszó hash-elése"""
    # Bcrypt 72 bájt limit kezelése
    if len(password.encode('utf-8')) > 72:
        password = password[:72]
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """JWT token létrehozása"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return encoded_jwt

def authenticate_user(db: Session, email: str, password: str) -> User | None:
    """Felhasználó autentikálása"""
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user

def create_user(
    db: Session,
    username: str,
    email: str,
    password: str,
    role: UserRole = UserRole.USER,
    created_by_id: int | None = None
) -> User:
    """Új felhasználó létrehozása"""
    # Ellenőrzés: létezik-e már
    existing = db.query(User).filter(
        (User.email == email) | (User.username == username)
    ).first()
    
    if existing:
        raise ValueError("Email vagy felhasználónév már foglalt")
    
    # Felhasználó létrehozása
    user = User(
        username=username,
        email=email,
        password_hash=get_password_hash(password),
        role=role,
        created_by_id=created_by_id
    )
    
    db.add(user)
    db.commit()
    db.refresh(user)
    
    return user

def verify_email_token(db: Session, token: str) -> User | None:
    """Email verifikációs token ellenőrzése"""
    user = db.query(User).filter(
        User.email_verification_token == token,
        User.email_verification_expires > datetime.utcnow()
    ).first()
    
    if user:
        user.email_verified = True
        user.email_verification_token = None
        user.email_verification_expires = None
        db.commit()
        db.refresh(user)
        return user
    
    return None


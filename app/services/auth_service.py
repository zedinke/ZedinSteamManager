"""
Autentikációs szolgáltatás
"""

from sqlalchemy.orm import Session
from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta
from app.database import User, UserRole
from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Jelszó ellenőrzése"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Jelszó hash-elése"""
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


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
        if pwd_context is None:
            # Közvetlenül bcrypt használata
            import bcrypt
            return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
        return pwd_context.verify(plain_password, hashed_password)
    except (ValueError, TypeError, AttributeError) as e:
        # Ha a hash formátuma nem megfelelő, próbáljuk meg közvetlenül bcrypt-tel
        try:
            import bcrypt
            return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
        except Exception as e2:
            print(f"Password verification error: {e}, bcrypt fallback error: {e2}")
            return False

def get_password_hash(password: str) -> str:
    """Jelszó hash-elése"""
    if not password:
        raise ValueError("Jelszó nem lehet üres")
    
    # Bcrypt 72 bájt limit kezelése
    password_bytes = password.encode('utf-8')
    if len(password_bytes) > 72:
        # 72 bájt = kb 72 karakter UTF-8-ban (egyszerű karakterek esetén)
        # De biztonságosabb, ha karaktereket számolunk, nem bájtokat
        password = password[:72]
        password_bytes = password.encode('utf-8')
        if len(password_bytes) > 72:
            # Ha még mindig túl hosszú (pl. multi-byte karakterek), vágjuk bájtokban
            password_bytes = password_bytes[:72]
            password = password_bytes.decode('utf-8', errors='ignore')
    
    try:
        if pwd_context is None:
            # Közvetlenül bcrypt használata
            import bcrypt
            salt = bcrypt.gensalt()
            return bcrypt.hashpw(password_bytes, salt).decode('utf-8')
        return pwd_context.hash(password)
    except (ValueError, AttributeError, TypeError) as e:
        # Ha még mindig probléma van, próbáljuk meg közvetlenül bcrypt-tel
        try:
            import bcrypt
            salt = bcrypt.gensalt()
            return bcrypt.hashpw(password_bytes, salt).decode('utf-8')
        except Exception as e2:
            raise ValueError(f"Jelszó hash-elés sikertelen: {e2}")

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


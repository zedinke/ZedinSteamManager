"""
FastAPI dependencies
"""

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from jose import JWTError, jwt
from app.database import get_db, User, UserRole
from app.config import settings

security = HTTPBearer()

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """Jelenlegi felhasználó lekérése JWT token-ből"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        token = credentials.credentials
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id: int = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception
    
    return user

def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Aktív felhasználó ellenőrzése"""
    if not current_user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email cím nincs megerősítve"
        )
    return current_user

def require_role(required_role: UserRole):
    """Jogosultság ellenőrző dependency factory"""
    role_hierarchy = {
        UserRole.USER: 1,
        UserRole.ADMIN: 2,
        UserRole.SERVER_ADMIN: 3,
        UserRole.MANAGER_ADMIN: 4
    }
    
    def role_checker(current_user: User = Depends(get_current_active_user)) -> User:
        user_level = role_hierarchy.get(current_user.role, 0)
        required_level = role_hierarchy.get(required_role, 0)
        
        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Szükséges jogosultság: {required_role.value}"
            )
        return current_user
    
    return role_checker

def require_manager_admin(request: Request, db: Session = Depends(get_db)) -> User:
    """Manager Admin jogosultság ellenőrzése session alapján"""
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_302_FOUND,
            detail="Nincs bejelentkezve",
            headers={"Location": "/login"}
        )
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user or user.role != UserRole.MANAGER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nincs jogosultságod - Manager Admin szükséges"
        )
    return user

# Session alapú dependency (cookie-khoz) - nincs használva, a require_login közvetlenül session-t használ


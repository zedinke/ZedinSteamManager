"""
Autentikációs router
"""

from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from datetime import timedelta
from app.database import get_db, User
from app.services.auth_service import (
    authenticate_user,
    create_user,
    verify_email_token,
    create_access_token,
    get_password_hash
)
from app.services.email_service import send_verification_email
from app.config import settings
from app.dependencies import require_login
from sqlalchemy.orm import Session
from app.database import get_db
import secrets
from datetime import datetime

router = APIRouter()

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, db: Session = Depends(get_db)):
    """Login oldal"""
    user_id = request.session.get("user_id")
    if user_id:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            return RedirectResponse(url="/dashboard", status_code=302)
    
    from app.main import get_templates
    templates = get_templates()
    return templates.TemplateResponse("auth/login.html", {"request": request})

@router.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """Bejelentkezés"""
    user = authenticate_user(db, email, password)
    
    if not user:
    from app.main import get_templates
    templates = get_templates()
    return templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "error": "Hibás email vagy jelszó"}
        )
    
    if not user.email_verified:
    from app.main import get_templates
    templates = get_templates()
    return templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "error": "Email cím nincs megerősítve"}
        )
    
    # Session létrehozása
    request.session["user_id"] = user.id
    request.session["user_role"] = user.role.value
    request.session["username"] = user.username
    
    return RedirectResponse(url="/dashboard", status_code=302)

@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, db: Session = Depends(get_db)):
    """Regisztráció oldal"""
    user_id = request.session.get("user_id")
    if user_id:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            return RedirectResponse(url="/dashboard", status_code=302)
    
    from app.main import get_templates
    templates = get_templates()
    return templates.TemplateResponse("auth/register.html", {"request": request})

@router.post("/register")
async def register(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    db: Session = Depends(get_db)
):
    """Regisztráció"""
    if password != password_confirm:
        from app.main import get_templates
        templates = get_templates()
        return templates.TemplateResponse(
            "auth/register.html",
            {"request": request, "error": "A jelszavak nem egyeznek"}
        )
    
    if len(password) < 8:
        from app.main import get_templates
        templates = get_templates()
        return templates.TemplateResponse(
            "auth/register.html",
            {"request": request, "error": "A jelszónak legalább 8 karakter hosszúnak kell lennie"}
        )
    
    try:
        # Email verifikációs token
        token = secrets.token_urlsafe(32)
        expires = datetime.utcnow() + timedelta(hours=24)
        
        user = create_user(db, username, email, password)
        
        # Token beállítása
        user.email_verification_token = token
        user.email_verification_expires = expires
        db.commit()
        
        # Email küldése
        await send_verification_email(email, username, token)
        
        from app.main import get_templates
        templates = get_templates()
        return templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "success": "Regisztráció sikeres! Kérjük, erősítse meg az email címét."}
        )
    except ValueError as e:
        from app.main import get_templates
        templates = get_templates()
        return templates.TemplateResponse(
            "auth/register.html",
            {"request": request, "error": str(e)}
        )

@router.get("/verify-email")
async def verify_email(
    request: Request,
    token: str,
    db: Session = Depends(get_db)
):
    """Email verifikáció"""
    user = verify_email_token(db, token)
    
    from app.main import get_templates
    templates = get_templates()
    if user:
        return templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "success": "Email cím sikeresen megerősítve! Most már bejelentkezhet."}
        )
    else:
        return templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "error": "Érvénytelen vagy lejárt token"}
        )

@router.get("/logout")
async def logout(request: Request):
    """Kijelentkezés"""
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)


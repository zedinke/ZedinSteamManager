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
import secrets
from datetime import datetime, timedelta

router = APIRouter()

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, db: Session = Depends(get_db)):
    """Login oldal"""
    user_id = request.session.get("user_id")
    if user_id:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            return RedirectResponse(url="/dashboard", status_code=302)
    
    # FONTOS: Ellenőrizzük, hogy ne jöjjön létre root jogosultságokkal mappa
    # Ha van session-ben user_id, ellenőrizzük a mappát
    if user_id:
        try:
            import os
            import stat
            from pathlib import Path
            from app.config import settings
            from app.services.symlink_service import get_user_serverfiles_path
            
            user_serverfiles_path = get_user_serverfiles_path(user_id)
            if user_serverfiles_path.exists():
                try:
                    stat_info = user_serverfiles_path.stat()
                    current_uid = os.getuid()
                    if stat_info.st_uid == 0 and current_uid != 0:
                        # Root jogosultságokkal létezik, próbáljuk meg javítani
                        try:
                            os.chmod(user_serverfiles_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
                            os.chown(user_serverfiles_path, current_uid, os.getgid())
                        except (PermissionError, OSError):
                            # Ha nem sikerül, próbáljuk meg átnevezni
                            try:
                                backup_path = user_serverfiles_path.parent / f"{user_serverfiles_path.name}.root_backup"
                                if backup_path.exists():
                                    import shutil
                                    shutil.rmtree(backup_path)
                                user_serverfiles_path.rename(backup_path)
                            except:
                                pass
                except (PermissionError, OSError):
                    pass
        except Exception:
            pass  # Ne akadályozza a login oldal betöltését
    
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
        # Felhasználóbarát hibaüzenet
        error_msg = str(e)
        if "password cannot be longer" in error_msg.lower() or "72 bytes" in error_msg.lower():
            error_msg = "A jelszó túl hosszú. Maximum 72 karakter lehet."
        return templates.TemplateResponse(
            "auth/register.html",
            {"request": request, "error": error_msg}
        )
    except Exception as e:
        from app.main import get_templates
        templates = get_templates()
        # Általános hibaüzenet
        error_msg = "Hiba történt a regisztráció során. Kérjük, próbálja újra."
        print(f"Registration error: {e}")
        return templates.TemplateResponse(
            "auth/register.html",
            {"request": request, "error": error_msg}
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


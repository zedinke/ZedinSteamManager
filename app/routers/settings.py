"""
Settings router - felhasználói beállítások
"""

from fastapi import APIRouter, Request, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.database import get_db, User
from app.services.auth_service import verify_password, get_password_hash
from app.main import get_templates

router = APIRouter()

@router.get("/settings/profile", response_class=HTMLResponse)
async def show_profile(request: Request, db: Session = Depends(get_db)):
    """Felhasználói profil oldal"""
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    
    current_user = db.query(User).filter(User.id == user_id).first()
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)
    
    templates = get_templates()
    return templates.TemplateResponse(
        "settings/profile.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.post("/settings/profile")
async def update_profile(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    db: Session = Depends(get_db)
):
    """Felhasználói profil frissítése"""
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    
    current_user = db.query(User).filter(User.id == user_id).first()
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)
    
    # Email ellenőrzés (ha változott, újra kell verifikálni)
    email_changed = current_user.email != email
    
    # Username és email frissítése
    current_user.username = username
    current_user.email = email
    
    if email_changed:
        current_user.email_verified = False
    
    db.commit()
    
    # Session frissítése
    request.session["username"] = username
    request.session["email"] = email
    
    request.session["success"] = "Profil sikeresen frissítve!"
    return RedirectResponse(url="/settings/profile", status_code=302)

@router.get("/settings/password", response_class=HTMLResponse)
async def show_password_change(request: Request, db: Session = Depends(get_db)):
    """Jelszó változtatás oldal"""
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    
    current_user = db.query(User).filter(User.id == user_id).first()
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)
    
    templates = get_templates()
    return templates.TemplateResponse(
        "settings/password.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.post("/settings/password")
async def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db)
):
    """Jelszó változtatás"""
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    
    current_user = db.query(User).filter(User.id == user_id).first()
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)
    
    # Jelenlegi jelszó ellenőrzése
    if not verify_password(current_password, current_user.password_hash):
        request.session["error"] = "Hibás jelenlegi jelszó!"
        return RedirectResponse(url="/settings/password", status_code=302)
    
    # Új jelszó ellenőrzése
    if len(new_password) < 8:
        request.session["error"] = "Az új jelszónak legalább 8 karakter hosszúnak kell lennie!"
        return RedirectResponse(url="/settings/password", status_code=302)
    
    if new_password != confirm_password:
        request.session["error"] = "Az új jelszavak nem egyeznek!"
        return RedirectResponse(url="/settings/password", status_code=302)
    
    # Jelszó frissítése
    current_user.password_hash = get_password_hash(new_password)
    db.commit()
    
    request.session["success"] = "Jelszó sikeresen megváltoztatva!"
    return RedirectResponse(url="/settings/password", status_code=302)


"""
Mod kezelő router - Server Admin mod csomagok kezelése
"""

from fastapi import APIRouter, Request, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from app.database import get_db, User, UserMod
from fastapi.templating import Jinja2Templates
from pathlib import Path

router = APIRouter(prefix="/mods", tags=["mods"])

# Template-ek inicializálása
BASE_DIR = Path(__file__).parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

def require_server_admin(request: Request, db: Session = Depends(get_db)) -> User:
    """Server Admin jogosultság ellenőrzése"""
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=302,
            detail="Nincs bejelentkezve",
            headers={"Location": "/login"}
        )
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user or user.role.value not in ["server_admin", "manager_admin"]:
        raise HTTPException(
            status_code=403,
            detail="Nincs jogosultságod - Server Admin szükséges"
        )
    return user

@router.get("", response_class=HTMLResponse)
async def list_mods(
    request: Request,
    db: Session = Depends(get_db)
):
    """Server Admin: Mod csomagok listája"""
    current_user = require_server_admin(request, db)
    
    mods = db.query(UserMod).filter(
        UserMod.user_id == current_user.id
    ).order_by(desc(UserMod.created_at)).all()
    
    return templates.TemplateResponse("mods/list.html", {
        "request": request,
        "current_user": current_user,
        "mods": mods
    })

@router.post("/add")
async def add_mod(
    request: Request,
    mod_id: str = Form(...),
    name: str = Form(...),
    icon_url: str = Form(None),
    curseforge_url: str = Form(None),
    description: str = Form(None),
    db: Session = Depends(get_db)
):
    """Server Admin: Mod hozzáadása a tárolóhoz"""
    current_user = require_server_admin(request, db)
    
    # Ellenőrizzük, hogy létezik-e már ilyen mod
    existing = db.query(UserMod).filter(
        and_(
            UserMod.user_id == current_user.id,
            UserMod.mod_id == mod_id
        )
    ).first()
    
    if existing:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "detail": "Ez a mod már hozzá van adva a tárolódhoz"
            }
        )
    
    # Új mod létrehozása
    user_mod = UserMod(
        user_id=current_user.id,
        mod_id=mod_id,
        name=name,
        icon_url=icon_url,
        curseforge_url=curseforge_url,
        description=description
    )
    
    db.add(user_mod)
    db.commit()
    db.refresh(user_mod)
    
    return JSONResponse({
        "success": True,
        "message": "Mod hozzáadva"
    })

@router.post("/{mod_id}/delete")
async def delete_mod(
    request: Request,
    mod_id: int,
    db: Session = Depends(get_db)
):
    """Server Admin: Mod törlése a tárolóból"""
    current_user = require_server_admin(request, db)
    
    # Ellenőrizzük, hogy a mod létezik-e
    mod = db.query(UserMod).filter(UserMod.id == mod_id).first()
    
    if not mod:
        return RedirectResponse(
            url="/mods?error=Mod+nem+található",
            status_code=303
        )
    
    # Ellenőrizzük, hogy a mod a felhasználóhoz tartozik-e
    if mod.user_id != current_user.id:
        return RedirectResponse(
            url="/mods?error=Nincs+jogosultságod+ezt+a+modot+törölni",
            status_code=303
        )
    
    mod_name = mod.name
    db.delete(mod)
    db.commit()
    
    return RedirectResponse(
        url=f"/mods?success={mod_name}+mod+sikeresen+törölve",
        status_code=303
    )

@router.get("/api/list")
async def api_list_mods(
    request: Request,
    db: Session = Depends(get_db)
):
    """API endpoint mod listához"""
    current_user = require_server_admin(request, db)
    
    mods = db.query(UserMod).filter(
        UserMod.user_id == current_user.id
    ).order_by(UserMod.name).all()
    
    return JSONResponse({
        "success": True,
        "mods": [
            {
                "id": mod.id,
                "mod_id": mod.mod_id,
                "name": mod.name,
                "icon_url": mod.icon_url
            }
            for mod in mods
        ]
    })


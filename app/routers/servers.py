"""
Servers router - Server Admin szerver indítás
"""

from fastapi import APIRouter, Request, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from app.database import get_db, User, Game, ServerInstance, ServerStatus, Token, TokenType
from app.dependencies import require_manager_admin
from fastapi.templating import Jinja2Templates
from pathlib import Path
from datetime import datetime

router = APIRouter(prefix="/servers", tags=["servers"])

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
async def list_servers(
    request: Request,
    db: Session = Depends(get_db)
):
    """Server Admin: Szerverek listája"""
    current_user = require_server_admin(request, db)
    
    # Csak az aktuális user szervereit mutatjuk
    servers = db.query(ServerInstance).filter(
        ServerInstance.server_admin_id == current_user.id
    ).order_by(desc(ServerInstance.created_at)).all()
    
    return templates.TemplateResponse("servers/list.html", {
        "request": request,
        "current_user": current_user,
        "servers": servers
    })

@router.get("/start", response_class=HTMLResponse)
async def show_start_server(
    request: Request,
    db: Session = Depends(get_db)
):
    """Server Admin: Szerver indítás form"""
    current_user = require_server_admin(request, db)
    
    # Csak az aktív játékokat mutatjuk
    games = db.query(Game).filter(Game.is_active == True).order_by(Game.name).all()
    
    # Ellenőrizzük, hogy van-e aktív token
    active_tokens = db.query(Token).filter(
        and_(
            Token.user_id == current_user.id,
            Token.is_active == True,
            Token.expires_at > datetime.now()
        )
    ).count()
    
    return templates.TemplateResponse("servers/start.html", {
        "request": request,
        "current_user": current_user,
        "games": games,
        "active_tokens": active_tokens
    })

@router.post("/start")
async def start_server(
    request: Request,
    game_id: int = Form(...),
    name: str = Form(...),
    port: int = Form(None),
    db: Session = Depends(get_db)
):
    """Server Admin: Szerver indítása"""
    current_user = require_server_admin(request, db)
    
    # Ellenőrizzük, hogy a játék létezik és aktív
    game = db.query(Game).filter(
        and_(Game.id == game_id, Game.is_active == True)
    ).first()
    if not game:
        raise HTTPException(status_code=404, detail="Játék nem található vagy nem aktív")
    
    # Ellenőrizzük, hogy van-e aktív token
    active_token = db.query(Token).filter(
        and_(
            Token.user_id == current_user.id,
            Token.is_active == True,
            Token.expires_at > datetime.now()
        )
    ).first()
    
    if not active_token:
        raise HTTPException(
            status_code=400,
            detail="Nincs aktív token! Szükséges 1 token a szerver indításához."
        )
    
    # Új szerver példány létrehozása
    server_instance = ServerInstance(
        game_id=game.id,
        server_admin_id=current_user.id,
        name=name,
        port=port,
        status=ServerStatus.RUNNING,
        token_used_id=active_token.id,
        started_at=datetime.now()
    )
    
    db.add(server_instance)
    
    # Token deaktiválása
    active_token.is_active = False
    
    db.commit()
    db.refresh(server_instance)
    
    return RedirectResponse(url="/servers", status_code=303)

@router.post("/{server_id}/stop")
async def stop_server(
    request: Request,
    server_id: int,
    db: Session = Depends(get_db)
):
    """Server Admin: Szerver leállítása"""
    current_user = require_server_admin(request, db)
    
    server = db.query(ServerInstance).filter(
        and_(
            ServerInstance.id == server_id,
            ServerInstance.server_admin_id == current_user.id
        )
    ).first()
    
    if not server:
        raise HTTPException(status_code=404, detail="Szerver nem található")
    
    server.status = ServerStatus.STOPPED
    server.stopped_at = datetime.now()
    db.commit()
    
    return JSONResponse({
        "success": True,
        "message": "Szerver leállítva"
    })

@router.post("/{server_id}/delete")
async def delete_server(
    request: Request,
    server_id: int,
    db: Session = Depends(get_db)
):
    """Server Admin: Szerver törlése"""
    current_user = require_server_admin(request, db)
    
    server = db.query(ServerInstance).filter(
        and_(
            ServerInstance.id == server_id,
            ServerInstance.server_admin_id == current_user.id
        )
    ).first()
    
    if not server:
        raise HTTPException(status_code=404, detail="Szerver nem található")
    
    db.delete(server)
    db.commit()
    
    return JSONResponse({
        "success": True,
        "message": "Szerver törölve"
    })


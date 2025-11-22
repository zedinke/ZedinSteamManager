"""
Servers router - Server Admin szerver indítás
"""

from fastapi import APIRouter, Request, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, asc
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
    
    # Token információk hozzáadása minden szerverhez
    from datetime import datetime, timedelta
    now = datetime.now()
    
    servers_data = []
    for server in servers:
        server_dict = {
            "server": server,
            "token_days_left": None,
            "deletion_days_left": None,
            "token_expired": False
        }
        
        if server.token_used_id and server.token_expires_at:
            # Token lejárat számítás
            if server.token_expires_at > now:
                days_left = (server.token_expires_at - now).days
                server_dict["token_days_left"] = days_left
                server_dict["token_expired"] = False
            else:
                server_dict["token_expired"] = True
                # Ha lejárt, akkor a törlési dátumot mutatjuk
                if server.scheduled_deletion_date:
                    if server.scheduled_deletion_date > now:
                        days_left = (server.scheduled_deletion_date - now).days
                        server_dict["deletion_days_left"] = days_left
                    else:
                        server_dict["deletion_days_left"] = 0
        
        servers_data.append(server_dict)
    
    return templates.TemplateResponse("servers/list.html", {
        "request": request,
        "current_user": current_user,
        "servers_data": servers_data
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
    # Számoljuk, hogy hány token van, ami NEM van használatban szerverrel
    active_tokens_count = db.query(Token).filter(
        and_(
            Token.user_id == current_user.id,
            Token.is_active == True,
            Token.expires_at > datetime.now()
        )
    ).count()
    
    # Számoljuk, hogy hány szerver van aktív token-nel
    used_tokens_count = db.query(ServerInstance).filter(
        and_(
            ServerInstance.server_admin_id == current_user.id,
            ServerInstance.token_used_id.isnot(None),
            ServerInstance.scheduled_deletion_date.is_(None)  # Még nem ütemezett törlésre
        )
    ).count()
    
    available_tokens = active_tokens_count - used_tokens_count
    
    return templates.TemplateResponse("servers/start.html", {
        "request": request,
        "current_user": current_user,
        "games": games,
        "active_tokens": available_tokens
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
    
    # Ellenőrizzük, hogy van-e elég aktív token
    # Számoljuk, hogy hány token van, ami NEM van használatban szerverrel
    active_tokens_count = db.query(Token).filter(
        and_(
            Token.user_id == current_user.id,
            Token.is_active == True,
            Token.expires_at > datetime.now()
        )
    ).count()
    
    # Számoljuk, hogy hány szerver van aktív token-nel
    used_tokens_count = db.query(ServerInstance).filter(
        and_(
            ServerInstance.server_admin_id == current_user.id,
            ServerInstance.token_used_id.isnot(None),
            ServerInstance.scheduled_deletion_date.is_(None)  # Még nem ütemezett törlésre
        )
    ).count()
    
    available_tokens = active_tokens_count - used_tokens_count
    
    if available_tokens <= 0:
        raise HTTPException(
            status_code=400,
            detail="Nincs elég aktív token! Szükséges 1 szabad aktív token a szerver indításához."
        )
    
    # Legrégebbi aktív token kiválasztása, ami NEM van használatban
    # Először keressük a tokeneket, amik nincsenek használatban
    used_token_ids_subq = db.query(ServerInstance.token_used_id).filter(
        and_(
            ServerInstance.server_admin_id == current_user.id,
            ServerInstance.token_used_id.isnot(None),
            ServerInstance.scheduled_deletion_date.is_(None)
        )
    ).subquery()
    
    # Legrégebbi token, ami nincs használatban
    from sqlalchemy import not_
    active_token = db.query(Token).filter(
        and_(
            Token.user_id == current_user.id,
            Token.is_active == True,
            Token.expires_at > datetime.now(),
            not_(Token.id.in_(db.query(used_token_ids_subq.c.token_used_id)))
        )
    ).order_by(asc(Token.created_at)).first()
    
    if not active_token:
        raise HTTPException(
            status_code=400,
            detail="Nincs elérhető aktív token! Szükséges 1 szabad aktív token a szerver indításához."
        )
    
    # 30 nap a token lejárata után a törlési dátum
    from datetime import timedelta
    scheduled_deletion = active_token.expires_at + timedelta(days=30)
    
    # Új szerver példány létrehozása
    server_instance = ServerInstance(
        game_id=game.id,
        server_admin_id=current_user.id,
        name=name,
        port=port,
        status=ServerStatus.RUNNING,
        token_used_id=active_token.id,
        token_expires_at=active_token.expires_at,
        scheduled_deletion_date=scheduled_deletion,
        started_at=datetime.now()
    )
    
    db.add(server_instance)
    # Token NEM deaktiváljuk!
    
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
    """Server Admin: Szerver törlése - token felszabadítása"""
    current_user = require_server_admin(request, db)
    
    server = db.query(ServerInstance).filter(
        and_(
            ServerInstance.id == server_id,
            ServerInstance.server_admin_id == current_user.id
        )
    ).first()
    
    if not server:
        raise HTTPException(status_code=404, detail="Szerver nem található")
    
    # Token felszabadítása (token_used_id = NULL)
    # A token marad aktív, hogy újra használható legyen
    server.token_used_id = None
    server.token_expires_at = None
    server.scheduled_deletion_date = None
    server.status = ServerStatus.STOPPED
    server.stopped_at = datetime.now()
    
    db.commit()
    
    return JSONResponse({
        "success": True,
        "message": "Szerver törölve, token felszabadítva"
    })


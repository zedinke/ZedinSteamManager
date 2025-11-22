"""
Ark Server router - Server Admin Ark szerver kezelés
"""

from fastapi import APIRouter, Request, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, asc
from app.database import get_db, User, Game, ServerInstance, ServerStatus, Token, TokenType, Cluster
from app.services.port_service import find_available_port, get_query_port, get_rcon_port
from app.services.symlink_service import create_server_symlink, remove_server_symlink
from fastapi.templating import Jinja2Templates
from pathlib import Path
from datetime import datetime, timedelta
import json

router = APIRouter(prefix="/ark", tags=["ark_servers"])

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

@router.get("/clusters", response_class=HTMLResponse)
async def list_clusters(
    request: Request,
    db: Session = Depends(get_db)
):
    """Server Admin: Cluster-ek listája"""
    current_user = require_server_admin(request, db)
    
    clusters = db.query(Cluster).filter(
        Cluster.server_admin_id == current_user.id
    ).order_by(desc(Cluster.created_at)).all()
    
    # Szerverek száma clusterenként
    for cluster in clusters:
        cluster.server_count = db.query(ServerInstance).filter(
            ServerInstance.cluster_id == cluster.id
        ).count()
    
    return templates.TemplateResponse("ark/clusters.html", {
        "request": request,
        "current_user": current_user,
        "clusters": clusters
    })

@router.get("/clusters/create", response_class=HTMLResponse)
async def show_create_cluster(
    request: Request,
    db: Session = Depends(get_db)
):
    """Server Admin: Cluster létrehozási form"""
    current_user = require_server_admin(request, db)
    
    return templates.TemplateResponse("ark/cluster_create.html", {
        "request": request,
        "current_user": current_user
    })

@router.post("/clusters/create")
async def create_cluster(
    request: Request,
    cluster_id: str = Form(...),
    name: str = Form(...),
    description: str = Form(None),
    db: Session = Depends(get_db)
):
    """Server Admin: Cluster létrehozása"""
    current_user = require_server_admin(request, db)
    
    # Cluster ID validálás (csak betűk, számok, aláhúzás, kötőjel)
    import re
    if not re.match(r'^[a-zA-Z0-9_-]+$', cluster_id):
        raise HTTPException(
            status_code=400,
            detail="A Cluster ID csak betűket, számokat, aláhúzást és kötőjelet tartalmazhat"
        )
    
    # Ellenőrizzük, hogy létezik-e már ilyen cluster_id
    existing = db.query(Cluster).filter(Cluster.cluster_id == cluster_id).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Ez a Cluster ID már foglalt"
        )
    
    # Cluster létrehozása
    cluster = Cluster(
        server_admin_id=current_user.id,
        cluster_id=cluster_id,
        name=name,
        description=description
    )
    
    db.add(cluster)
    db.commit()
    db.refresh(cluster)
    
    return RedirectResponse(
        url="/ark/clusters?success=Cluster+létrehozva",
        status_code=302
    )

@router.post("/clusters/{cluster_id}/delete")
async def delete_cluster(
    request: Request,
    cluster_id: int,
    db: Session = Depends(get_db)
):
    """Server Admin: Cluster törlése"""
    current_user = require_server_admin(request, db)
    
    # Cluster lekérése
    cluster = db.query(Cluster).filter(
        and_(
            Cluster.id == cluster_id,
            Cluster.server_admin_id == current_user.id
        )
    ).first()
    
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster nem található")
    
    # Ellenőrizzük, hogy van-e hozzárendelt szerver
    servers_count = db.query(ServerInstance).filter(
        ServerInstance.cluster_id == cluster.id
    ).count()
    
    if servers_count > 0:
        return RedirectResponse(
            url=f"/ark/clusters?error=A+cluster+törlése+előtt+először+törölni+kell+a+hozzárendelt+szerevereket+({servers_count}+szerver)",
            status_code=302
        )
    
    # Cluster törlése
    db.delete(cluster)
    db.commit()
    
    return RedirectResponse(
        url="/ark/clusters?success=Cluster+törölve",
        status_code=302
    )

@router.get("/servers/create", response_class=HTMLResponse)
async def show_create_server(
    request: Request,
    db: Session = Depends(get_db)
):
    """Server Admin: Ark szerver létrehozási form"""
    current_user = require_server_admin(request, db)
    
    # Ark játék lekérése
    ark_game = db.query(Game).filter(Game.name.ilike("%ark%")).first()
    if not ark_game:
        raise HTTPException(
            status_code=404,
            detail="Ark Survival Ascended játék nem található. Kérlek, vedd fel a kapcsolatot a Manager Adminisztrátorral."
        )
    
    # Cluster-ek lekérése
    clusters = db.query(Cluster).filter(
        Cluster.server_admin_id == current_user.id
    ).order_by(Cluster.name).all()
    
    if not clusters:
        return RedirectResponse(
            url="/ark/clusters/create?error=Először+hozz+létre+egy+Cluster-t!",
            status_code=302
        )
    
    # Ellenőrizzük, hogy van-e elég aktív token
    active_tokens_count = db.query(Token).filter(
        and_(
            Token.user_id == current_user.id,
            Token.is_active == True,
            Token.expires_at > datetime.now()
        )
    ).count()
    
    used_tokens_count = db.query(ServerInstance).filter(
        and_(
            ServerInstance.server_admin_id == current_user.id,
            ServerInstance.token_used_id.isnot(None),
            ServerInstance.scheduled_deletion_date.is_(None)
        )
    ).count()
    
    available_tokens = active_tokens_count - used_tokens_count
    
    return templates.TemplateResponse("ark/server_create.html", {
        "request": request,
        "current_user": current_user,
        "ark_game": ark_game,
        "clusters": clusters,
        "available_tokens": available_tokens
    })

@router.post("/servers/create")
async def create_server(
    request: Request,
    cluster_id: int = Form(...),
    name: str = Form(...),
    max_players: int = Form(40),
    active_mods: str = Form(None),  # JSON string vagy comma-separated
    passive_mods: str = Form(None),
    db: Session = Depends(get_db)
):
    """Server Admin: Ark szerver létrehozása"""
    current_user = require_server_admin(request, db)
    
    # Cluster ellenőrzése
    cluster = db.query(Cluster).filter(
        and_(
            Cluster.id == cluster_id,
            Cluster.server_admin_id == current_user.id
        )
    ).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster nem található")
    
    # Ark játék lekérése
    ark_game = db.query(Game).filter(Game.name.ilike("%ark%")).first()
    if not ark_game:
        raise HTTPException(status_code=404, detail="Ark játék nem található")
    
    # Token ellenőrzése
    active_tokens_count = db.query(Token).filter(
        and_(
            Token.user_id == current_user.id,
            Token.is_active == True,
            Token.expires_at > datetime.now()
        )
    ).count()
    
    used_tokens_count = db.query(ServerInstance).filter(
        and_(
            ServerInstance.server_admin_id == current_user.id,
            ServerInstance.token_used_id.isnot(None),
            ServerInstance.scheduled_deletion_date.is_(None)
        )
    ).count()
    
    available_tokens = active_tokens_count - used_tokens_count
    
    if available_tokens <= 0:
        raise HTTPException(
            status_code=400,
            detail="Nincs elég aktív token! Szükséges 1 szabad aktív token a szerver létrehozásához."
        )
    
    # Legrégebbi aktív token kiválasztása
    used_token_ids_subq = db.query(ServerInstance.token_used_id).filter(
        and_(
            ServerInstance.server_admin_id == current_user.id,
            ServerInstance.token_used_id.isnot(None),
            ServerInstance.scheduled_deletion_date.is_(None)
        )
    ).subquery()
    
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
            detail="Nincs elérhető aktív token!"
        )
    
    # Port hozzárendelés - csak Ark szerver portokat nézünk (7777-től)
    game_port = find_available_port(db=db)
    if not game_port:
        raise HTTPException(
            status_code=500,
            detail="Nem sikerült elérhető portot találni"
        )
    
    query_port = get_query_port(game_port, db)
    rcon_port = get_rcon_port(game_port, db)
    
    # Modok feldolgozása
    active_mods_list = None
    if active_mods:
        try:
            # Ha JSON string
            if active_mods.strip().startswith('['):
                active_mods_list = json.loads(active_mods)
            else:
                # Ha comma-separated
                active_mods_list = [int(m.strip()) for m in active_mods.split(',') if m.strip().isdigit()]
        except (json.JSONDecodeError, ValueError):
            active_mods_list = None
    
    passive_mods_list = None
    if passive_mods:
        try:
            if passive_mods.strip().startswith('['):
                passive_mods_list = json.loads(passive_mods)
            else:
                passive_mods_list = [int(m.strip()) for m in passive_mods.split(',') if m.strip().isdigit()]
        except (json.JSONDecodeError, ValueError):
            passive_mods_list = None
    
    # Symlink-et később hozzuk létre, amikor már van server_id
    
    # Szerver létrehozása
    server_instance = ServerInstance(
        game_id=ark_game.id,
        server_admin_id=current_user.id,
        cluster_id=cluster.id,
        name=name,
        port=game_port,
        query_port=query_port,
        rcon_port=rcon_port,
        max_players=max_players,
        status=ServerStatus.STOPPED,
        active_mods=active_mods_list,
        passive_mods=passive_mods_list,
        token_used_id=active_token.id,
        token_expires_at=active_token.expires_at,
        scheduled_deletion_date=active_token.expires_at + timedelta(days=30),
        started_at=None
    )
    
    db.add(server_instance)
    db.commit()
    db.refresh(server_instance)
    
    # Most már frissíthetjük a server_path-et
    server_path = create_server_symlink(server_instance.id, cluster.cluster_id, db)
    if server_path:
        server_instance.server_path = str(server_path)
        db.commit()
    
    return RedirectResponse(
        url="/ark/servers?success=Szerver+létrehozva",
        status_code=302
    )

@router.get("/servers", response_class=HTMLResponse)
async def list_servers(
    request: Request,
    db: Session = Depends(get_db)
):
    """Server Admin: Ark szerverek listája"""
    current_user = require_server_admin(request, db)
    
    servers = db.query(ServerInstance).join(Game).filter(
        and_(
            ServerInstance.server_admin_id == current_user.id,
            Game.name.ilike("%ark%")
        )
    ).order_by(desc(ServerInstance.created_at)).all()
    
    # Token információk
    now = datetime.now()
    servers_data = []
    for server in servers:
        server_dict = {
            "server": server,
            "token_days_left": None,
            "token_expired": False
        }
        
        if server.token_used_id and server.token_expires_at:
            if server.token_expires_at > now:
                days_left = (server.token_expires_at - now).days
                server_dict["token_days_left"] = days_left
            else:
                server_dict["token_expired"] = True
        
        servers_data.append(server_dict)
    
    return templates.TemplateResponse("ark/servers.html", {
        "request": request,
        "current_user": current_user,
        "servers_data": servers_data
    })

@router.get("/servers/{server_id}/edit", response_class=HTMLResponse)
async def show_edit_server(
    request: Request,
    server_id: int,
    db: Session = Depends(get_db)
):
    """Server Admin: Ark szerver szerkesztése (modok, cluster)"""
    current_user = require_server_admin(request, db)
    
    server = db.query(ServerInstance).filter(
        and_(
            ServerInstance.id == server_id,
            ServerInstance.server_admin_id == current_user.id
        )
    ).first()
    
    if not server:
        raise HTTPException(status_code=404, detail="Szerver nem található")
    
    # Cluster-ek
    clusters = db.query(Cluster).filter(
        Cluster.server_admin_id == current_user.id
    ).order_by(Cluster.name).all()
    
    return templates.TemplateResponse("ark/server_edit.html", {
        "request": request,
        "current_user": current_user,
        "server": server,
        "clusters": clusters
    })

@router.post("/servers/{server_id}/delete")
async def delete_server(
    request: Request,
    server_id: int,
    db: Session = Depends(get_db)
):
    """Server Admin: Ark szerver törlése"""
    current_user = require_server_admin(request, db)
    
    # Szerver lekérése
    server = db.query(ServerInstance).filter(
        and_(
            ServerInstance.id == server_id,
            ServerInstance.server_admin_id == current_user.id
        )
    ).first()
    
    if not server:
        raise HTTPException(status_code=404, detail="Szerver nem található")
    
    # Ha fut a szerver, akkor először le kell állítani
    if server.status == ServerStatus.RUNNING:
        return RedirectResponse(
            url=f"/ark/servers?error=A+szerver+törlése+előtt+először+le+kell+állítani",
            status_code=302
        )
    
    # Symlink eltávolítása (ha létezik)
    try:
        cluster = db.query(Cluster).filter(Cluster.id == server.cluster_id).first() if server.cluster_id else None
        cluster_id_str = cluster.cluster_id if cluster else None
        remove_server_symlink(server.id, cluster_id_str)
    except Exception as e:
        # Ha hiba van, csak logoljuk, de ne akadályozza a törlést
        print(f"Figyelmeztetés: Symlink eltávolítása sikertelen: {e}")
    
    # Szerver törlése
    db.delete(server)
    db.commit()
    
    return RedirectResponse(
        url="/ark/servers?success=Szerver+törölve",
        status_code=302
    )

@router.post("/servers/{server_id}/edit")
async def edit_server(
    request: Request,
    server_id: int,
    cluster_id: int = Form(...),
    active_mods: str = Form(None),
    passive_mods: str = Form(None),
    db: Session = Depends(get_db)
):
    """Server Admin: Ark szerver módosítása"""
    current_user = require_server_admin(request, db)
    
    server = db.query(ServerInstance).filter(
        and_(
            ServerInstance.id == server_id,
            ServerInstance.server_admin_id == current_user.id
        )
    ).first()
    
    if not server:
        raise HTTPException(status_code=404, detail="Szerver nem található")
    
    # Cluster ellenőrzése
    cluster = db.query(Cluster).filter(
        and_(
            Cluster.id == cluster_id,
            Cluster.server_admin_id == current_user.id
        )
    ).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster nem található")
    
    # Modok feldolgozása
    active_mods_list = None
    if active_mods:
        try:
            if active_mods.strip().startswith('['):
                active_mods_list = json.loads(active_mods)
            else:
                active_mods_list = [int(m.strip()) for m in active_mods.split(',') if m.strip().isdigit()]
        except (json.JSONDecodeError, ValueError):
            active_mods_list = None
    
    passive_mods_list = None
    if passive_mods:
        try:
            if passive_mods.strip().startswith('['):
                passive_mods_list = json.loads(passive_mods)
            else:
                passive_mods_list = [int(m.strip()) for m in passive_mods.split(',') if m.strip().isdigit()]
        except (json.JSONDecodeError, ValueError):
            passive_mods_list = None
    
    # Frissítés
    old_cluster_id = server.cluster_id
    server.cluster_id = cluster.id
    server.active_mods = active_mods_list
    server.passive_mods = passive_mods_list
    
    # Ha változott a cluster, akkor újra kell hozni a symlink-et
    if old_cluster_id != cluster.id:
        # Régi cluster ID lekérése
        old_cluster = db.query(Cluster).filter(Cluster.id == old_cluster_id).first() if old_cluster_id else None
        old_cluster_id_str = old_cluster.cluster_id if old_cluster else None
        
        remove_server_symlink(server.id, old_cluster_id_str)
        server_path = create_server_symlink(server.id, cluster.cluster_id, db)
        if server_path:
            server.server_path = str(server_path)
    
    db.commit()
    
    return RedirectResponse(
        url=f"/ark/servers?success=Szerver+módosítva",
        status_code=302
    )


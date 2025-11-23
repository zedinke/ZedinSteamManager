"""
Ark Server router - Server Admin Ark szerver kezelés
"""

from fastapi import APIRouter, Request, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, asc
from app.database import get_db, User, Game, ServerInstance, ServerStatus, Token, TokenType, Cluster, UserServerFiles
from app.services.port_service import find_available_port, get_query_port, get_rcon_port
from app.services.symlink_service import create_server_symlink, remove_server_symlink, get_server_path
from app.services.ark_config_service import update_config_from_server_settings
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
    # Szerver beállítások
    map_name: str = Form("TheIsland"),
    battleeye: str = Form(None),
    api: str = Form(None),
    rcon_enabled: str = Form(None),
    random_startup_delay: str = Form(None),
    cpu_optimization: str = Form(None),
    enable_motd: str = Form(None),
    show_admin_commands_in_chat: str = Form(None),
    motd: str = Form(None),
    motd_duration: int = Form(30),
    custom_server_args: str = Form(None),
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
    
    # Szerver konfiguráció összeállítása
    # session_name = name (a szerver név lesz a session name)
    server_config = {
        "TZ": "Europe/Budapest",  # Alapértelmezett időzóna
        "MAP_NAME": map_name,
        "SESSION_NAME": name,  # A szerver név lesz a session name
        "BATTLEEYE": battleeye == "true",
        "API": api == "true",
        "RCON_ENABLED": rcon_enabled == "true" if rcon_enabled else True,
        "RANDOM_STARTUP_DELAY": random_startup_delay == "true" if random_startup_delay else True,
        "CPU_OPTIMIZATION": cpu_optimization == "true" if cpu_optimization else True,
        "ENABLE_MOTD": enable_motd == "true" if enable_motd else True,
        "SHOW_ADMIN_COMMANDS_IN_CHAT": show_admin_commands_in_chat == "true",
    }
    
    if motd:
        server_config["MOTD"] = motd
        server_config["MOTD_DURATION"] = motd_duration
    
    if custom_server_args:
        server_config["CUSTOM_SERVER_ARGS"] = custom_server_args.strip()
    
    # Symlink-et később hozzuk létre, amikor már van server_id
    
    # Alapértelmezett RAM limit lekérése
    from app.database import SystemSettings
    default_ram_setting = db.query(SystemSettings).filter(SystemSettings.key == "default_ram_limit_gb").first()
    if default_ram_setting:
        try:
            default_ram_limit = int(default_ram_setting.value)
        except (ValueError, TypeError):
            from app.config import settings
            default_ram_limit = getattr(settings, 'default_ram_limit_gb', 8)
    else:
        from app.config import settings
        default_ram_limit = getattr(settings, 'default_ram_limit_gb', 8)
    
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
        config=server_config,
        active_mods=active_mods_list,
        passive_mods=passive_mods_list,
        token_used_id=active_token.id,
        token_expires_at=active_token.expires_at,
        scheduled_deletion_date=active_token.expires_at + timedelta(days=30),
        started_at=None,
        ram_limit_gb=default_ram_limit,
        purchased_ram_gb=0
    )
    
    db.add(server_instance)
    db.commit()
    db.refresh(server_instance)
    
    # Most már frissíthetjük a server_path-et
    # Ellenőrizzük, hogy van-e aktív felhasználó szerverfájl
    active_user_files = db.query(UserServerFiles).filter(
        and_(
            UserServerFiles.user_id == current_user.id,
            UserServerFiles.is_active == True,
            UserServerFiles.installation_status == "completed"
        )
    ).first()
    
    # Szerverfájlok használata (felhasználó vagy Manager Admin)
    server_dir = create_server_symlink(server_instance.id, cluster.cluster_id, db)
    if server_dir:
        # server_dir most már a Servers/server_{server_id}/ mappa
        server_instance.server_path = str(server_dir)
        db.commit()
        
        # ServerFiles symlink és Saved mappa útvonalai
        serverfiles_link = server_dir / "ServerFiles"
        saved_path = server_dir / "Saved"
        
        # Konfigurációs fájlok frissítése szerver létrehozásakor
        from app.services.ark_config_service import update_config_from_server_settings
        # RCON port beállítása - alapértelmezett 27015 (Ark alapértelmezett RCON port), vagy a szerver rcon_port értéke
        rcon_port_value = server_instance.rcon_port if server_instance.rcon_port else 27015
        
        update_config_from_server_settings(
            server_path=serverfiles_link,  # A ServerFiles symlink-et adjuk át
            session_name=name,  # A szerver név lesz a session name
            max_players=max_players,
            rcon_enabled=True,  # Alapértelmezett: engedélyezve
            rcon_port=rcon_port_value
        )
        
        # Docker Compose fájl létrehozása szerver létrehozásakor (mindig, még akkor is, ha Docker nem elérhető)
        from app.services.server_control_service import create_docker_compose_file
        try:
            if saved_path.exists():
                create_docker_compose_file(server_instance, serverfiles_link, saved_path)
                print(f"Docker Compose fájl létrehozva szerver létrehozásakor: {server_instance.id}")
            else:
                print(f"Figyelmeztetés: Saved mappa nem található: {saved_path}")
        except Exception as e:
            # Ha hiba van, csak logoljuk, de ne akadályozza a szerver létrehozását
            print(f"Figyelmeztetés: Docker Compose fájl létrehozása sikertelen: {e}")
            import traceback
            traceback.print_exc()
    
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
    
    # Token információk és indítási parancsok
    now = datetime.now()
    from app.services.server_control_service import get_start_command_string
    servers_data = []
    for server in servers:
        server_dict = {
            "server": server,
            "token_days_left": None,
            "token_expired": False,
            "start_command": get_start_command_string(server, db)
        }
        
        if server.token_used_id and server.token_expires_at:
            if server.token_expires_at > now:
                days_left = (server.token_expires_at - now).days
                server_dict["token_days_left"] = days_left
            else:
                server_dict["token_expired"] = True
        
        servers_data.append(server_dict)
    
    # Manager Admin jogosultság ellenőrzése
    is_manager_admin = current_user.role.value == "manager_admin"
    
    # RAM árazás lekérése (ha Manager Admin)
    ram_pricing = None
    if is_manager_admin:
        from app.database import RamPricing
        ram_pricing = db.query(RamPricing).order_by(RamPricing.updated_at.desc()).first()
    
    return templates.TemplateResponse("ark/servers.html", {
        "request": request,
        "current_user": current_user,
        "servers_data": servers_data,
        "is_manager_admin": is_manager_admin,
        "ram_pricing": ram_pricing
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
    
    # Instance mappa törlése (Docker Compose fájlokkal együtt)
    try:
        from app.services.server_control_service import remove_instance_dir
        remove_instance_dir(server.id)
    except Exception as e:
        # Ha hiba van, csak logoljuk, de ne akadályozza a törlést
        print(f"Figyelmeztetés: Instance mappa törlése sikertelen: {e}")
    
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
    # Szerver beállítások
    timezone: str = Form(None),
    map_name: str = Form(None),
    session_name: str = Form(None),
    server_admin_password: str = Form(None),
    server_password: str = Form(None),
    battleeye: str = Form(None),
    api: str = Form(None),
    rcon_enabled: str = Form(None),
    display_manager_monitor_message: str = Form(None),
    random_startup_delay: str = Form(None),
    cpu_optimization: str = Form(None),
    enable_motd: str = Form(None),
    show_admin_commands_in_chat: str = Form(None),
    motd: str = Form(None),
    motd_duration: int = Form(None),
    auto_backup_interval: str = Form(None),
    custom_server_args: str = Form(None),
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
    
    # Port ellenőrzés és frissítés, ha szükséges
    port_changed = False
    original_port = server.port
    original_query_port = server.query_port
    original_rcon_port = server.rcon_port
    
    # Ellenőrizzük, hogy a jelenlegi portok elérhetőek-e
    from app.services.port_service import check_port_available, get_query_port, get_rcon_port
    
    # Game port ellenőrzése
    if server.port and not check_port_available(server.port):
        # Ha foglalt, keressünk egy szabad portot
        new_port = find_available_port(start_port=server.port, db=db)
        if new_port:
            server.port = new_port
            port_changed = True
            print(f"Port foglalt volt ({original_port}), új port: {new_port}")
    
    # Query port ellenőrzése és frissítése (game port alapján)
    if server.port:
        new_query_port = get_query_port(server.port, db)
        if new_query_port != server.query_port:
            server.query_port = new_query_port
            port_changed = True
            print(f"Query port frissítve: {original_query_port} -> {new_query_port}")
    
    # RCON port ellenőrzése és frissítése (game port alapján)
    if server.port:
        new_rcon_port = get_rcon_port(server.port, db)
        if new_rcon_port != server.rcon_port:
            server.rcon_port = new_rcon_port
            port_changed = True
            print(f"RCON port frissítve: {original_rcon_port} -> {new_rcon_port}")
    
    # Frissítés
    old_cluster_id = server.cluster_id
    server.cluster_id = cluster.id
    server.active_mods = active_mods_list
    server.passive_mods = passive_mods_list
    
    # Config JSON frissítése
    # Fontos: másoljuk a config-ot, hogy ne módosítsuk közvetlenül az eredeti objektumot
    import copy
    server_config = copy.deepcopy(server.config) if server.config else {}
    
    # Beállítások frissítése a config JSON-ban
    if timezone:
        server_config["TZ"] = timezone
    if map_name:
        server_config["MAP_NAME"] = map_name
    if session_name:
        server_config["SESSION_NAME"] = session_name
    if server_admin_password and server_admin_password.strip():
        server_config["ServerAdminPassword"] = server_admin_password
    if server_password is not None:
        if server_password.strip():
            server_config["ServerPassword"] = server_password
        else:
            server_config.pop("ServerPassword", None)
    if battleeye:
        server_config["BATTLEEYE"] = battleeye == "true"
    if api:
        server_config["API"] = api == "true"
    if rcon_enabled:
        server_config["RCON_ENABLED"] = rcon_enabled == "true"
    if display_manager_monitor_message:
        server_config["DISPLAY_MANAGER_MONITOR_MESSAGE"] = display_manager_monitor_message == "true"
    if random_startup_delay:
        server_config["RANDOM_STARTUP_DELAY"] = random_startup_delay == "true"
    if cpu_optimization:
        server_config["CPU_OPTIMIZATION"] = cpu_optimization == "true"
    if enable_motd:
        server_config["ENABLE_MOTD"] = enable_motd == "true"
    if show_admin_commands_in_chat:
        server_config["SHOW_ADMIN_COMMANDS_IN_CHAT"] = show_admin_commands_in_chat == "true"
    if motd:
        server_config["MOTD"] = motd
    if motd_duration is not None:
        server_config["MOTD_DURATION"] = motd_duration
    # Automatikus backup intervallum kezelése
    print(f"DEBUG: auto_backup_interval értéke: {auto_backup_interval}, típus: {type(auto_backup_interval)}")
    if auto_backup_interval is not None:
        # Ha van érték és nem üres string
        if auto_backup_interval and str(auto_backup_interval).strip():
            try:
                interval_value = int(str(auto_backup_interval).strip())
                server_config["AUTO_BACKUP_INTERVAL"] = interval_value
                print(f"DEBUG: AUTO_BACKUP_INTERVAL beállítva: {interval_value}")
            except (ValueError, AttributeError) as e:
                # Ha nem lehet int-té konvertálni, akkor töröljük
                print(f"DEBUG: AUTO_BACKUP_INTERVAL konverzió hiba: {e}")
                server_config.pop("AUTO_BACKUP_INTERVAL", None)
        else:
            # Üres string esetén töröljük
            print(f"DEBUG: AUTO_BACKUP_INTERVAL törölve (üres string)")
            server_config.pop("AUTO_BACKUP_INTERVAL", None)
    else:
        print(f"DEBUG: auto_backup_interval None, nem változtatunk")
    
    print(f"DEBUG: Végleges server_config AUTO_BACKUP_INTERVAL: {server_config.get('AUTO_BACKUP_INTERVAL')}")
    if custom_server_args:
        server_config["CUSTOM_SERVER_ARGS"] = custom_server_args.strip()
    
    server.config = server_config
    
    # Debug: ellenőrizzük, hogy mentődött-e a config
    print(f"DEBUG: Server config mentés előtt: {server.config}")
    
    # Ha változott a cluster, akkor újra kell hozni a symlink-et
    if old_cluster_id != cluster.id:
        # Régi cluster ID lekérése
        old_cluster = db.query(Cluster).filter(Cluster.id == old_cluster_id).first() if old_cluster_id else None
        old_cluster_id_str = old_cluster.cluster_id if old_cluster else None
        
        remove_server_symlink(server.id, old_cluster_id_str)
        server_path = create_server_symlink(server.id, cluster.cluster_id, db)
        if server_path:
            server.server_path = str(server_path)
    else:
        # Ha nem változott a cluster, akkor is lekérjük a szerver útvonalat
        if server.server_path:
            server_path = Path(server.server_path)
        else:
            server_path = get_server_path(server.id, cluster.cluster_id, server.server_admin_id)
    
    # Commit előtt még egyszer ellenőrizzük
    print(f"DEBUG: Server config commit előtt: {server.config}")
    print(f"DEBUG: AUTO_BACKUP_INTERVAL commit előtt: {server.config.get('AUTO_BACKUP_INTERVAL')}")
    
    # Explicit módon beállítjuk a config-ot újra, hogy biztos legyen
    server.config = server_config
    
    # SQLAlchemy flag_modified használata - explicit jelzés, hogy a JSON mező módosult
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(server, "config")
    
    db.commit()
    
    # Újra lekérjük az adatbázisból, hogy lássuk, mi van benne
    db.expire(server, ['config'])
    db.refresh(server, ['config'])
    print(f"DEBUG: Server config commit után: {server.config}")
    print(f"DEBUG: AUTO_BACKUP_INTERVAL commit után: {server.config.get('AUTO_BACKUP_INTERVAL')}")
    
    # Konfigurációs fájlok frissítése
    if server_path and server_path.exists():
        # Új struktúra: server_path most már a Servers/server_{server_id}/ mappa
        # A ServerFiles symlink: server_path / "ServerFiles"
        serverfiles_link = server_path / "ServerFiles"
        if serverfiles_link.exists() and serverfiles_link.is_symlink():
            # RCON port beállítása - alapértelmezett 27015 (Ark alapértelmezett RCON port), vagy a szerver rcon_port értéke
            rcon_port_value = server.rcon_port if server.rcon_port else 27015
            
            update_config_from_server_settings(
                server_path=serverfiles_link,  # A ServerFiles symlink-et adjuk át
                session_name=session_name or server_config.get("SESSION_NAME"),
                server_admin_password=server_admin_password if server_admin_password and server_admin_password.strip() else None,
                server_password=server_password if server_password is not None else None,
                max_players=server.max_players,
                rcon_enabled=rcon_enabled == "true" if rcon_enabled else server_config.get("RCON_ENABLED", True),
                rcon_port=rcon_port_value,
                motd=motd or server_config.get("MOTD"),
                motd_duration=motd_duration if motd_duration is not None else server_config.get("MOTD_DURATION")
            )
    
    return RedirectResponse(
        url=f"/ark/servers?success=Szerver+módosítva",
        status_code=302
    )

@router.post("/servers/{server_id}/start")
async def start_server_endpoint(
    request: Request,
    server_id: int,
    db: Session = Depends(get_db)
):
    """Server Admin: Ark szerver indítása"""
    current_user = require_server_admin(request, db)
    
    server = db.query(ServerInstance).filter(
        and_(
            ServerInstance.id == server_id,
            ServerInstance.server_admin_id == current_user.id
        )
    ).first()
    
    if not server:
        raise HTTPException(status_code=404, detail="Szerver nem található")
    
    from app.services.server_control_service import start_server
    result = start_server(server, db)
    
    if result["success"]:
        return RedirectResponse(
            url=f"/ark/servers?success={result['message']}",
            status_code=302
        )
    else:
        return RedirectResponse(
            url=f"/ark/servers?error={result['message']}",
            status_code=302
        )

@router.post("/servers/{server_id}/stop")
async def stop_server_endpoint(
    request: Request,
    server_id: int,
    db: Session = Depends(get_db)
):
    """Server Admin: Ark szerver leállítása"""
    current_user = require_server_admin(request, db)
    
    server = db.query(ServerInstance).filter(
        and_(
            ServerInstance.id == server_id,
            ServerInstance.server_admin_id == current_user.id
        )
    ).first()
    
    if not server:
        raise HTTPException(status_code=404, detail="Szerver nem található")
    
    from app.services.server_control_service import stop_server
    result = stop_server(server, db)
    
    if result["success"]:
        return RedirectResponse(
            url=f"/ark/servers?success={result['message']}",
            status_code=302
        )
    else:
        return RedirectResponse(
            url=f"/ark/servers?error={result['message']}",
            status_code=302
        )

@router.post("/servers/{server_id}/restart")
async def restart_server_endpoint(
    request: Request,
    server_id: int,
    db: Session = Depends(get_db)
):
    """Server Admin: Ark szerver újraindítása"""
    current_user = require_server_admin(request, db)
    
    server = db.query(ServerInstance).filter(
        and_(
            ServerInstance.id == server_id,
            ServerInstance.server_admin_id == current_user.id
        )
    ).first()
    
    if not server:
        raise HTTPException(status_code=404, detail="Szerver nem található")
    
    from app.services.server_control_service import restart_server
    result = restart_server(server, db)
    
    if result["success"]:
        return RedirectResponse(
            url=f"/ark/servers?success={result['message']}",
            status_code=302
        )
    else:
        return RedirectResponse(
            url=f"/ark/servers?error={result['message']}",
            status_code=302
        )

@router.post("/servers/{server_id}/ram-limit")
async def set_ram_limit(
    request: Request,
    server_id: int,
    ram_limit_gb: int = Form(...),
    db: Session = Depends(get_db)
):
    """Manager Admin: RAM limit beállítása szerverenként"""
    from app.dependencies import require_manager_admin
    current_user = require_manager_admin(request, db)
    
    server = db.query(ServerInstance).filter(ServerInstance.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Szerver nem található")
    
    if ram_limit_gb < 0:
        raise HTTPException(status_code=400, detail="A RAM limit nem lehet negatív")
    
    server.ram_limit_gb = ram_limit_gb if ram_limit_gb > 0 else None
    db.commit()
    
    # Docker Compose fájl frissítése, ha fut a szerver
    if server.status == ServerStatus.RUNNING:
        from app.services.server_control_service import create_docker_compose_file
        from app.services.symlink_service import get_servers_base_path
        
        servers_base = get_servers_base_path()
        server_path = servers_base / f"server_{server.id}"
        serverfiles_link = server_path / "ServerFiles"
        saved_path = server_path / "Saved"
        
        if serverfiles_link.exists() and saved_path.exists():
            create_docker_compose_file(server, serverfiles_link, saved_path)
            # Szerver újraindítása, hogy a memória limit életbe lépjen
            from app.services.server_control_service import restart_server
            restart_server(server, db)
    
    return RedirectResponse(
        url=f"/ark/servers?success=RAM+limit+beállítva",
        status_code=302
    )


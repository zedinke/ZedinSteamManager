"""
Ark Server router - Server Admin Ark szerver kezelés
"""

from fastapi import APIRouter, Request, Form, HTTPException, Depends, Query
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
import threading
import time
import logging
import subprocess

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ark", tags=["ark_servers"])

# Scheduled shutdown tárolás: {server_id: shutdown_datetime}
scheduled_shutdowns = {}
shutdown_lock = threading.Lock()

def schedule_server_shutdown(server_id: int, minutes: int, db: Session):
    """Háttérfolyamat, ami késleltetve leállítja a szervert - minden percnél és 30mp-től másodpercenként chat üzenetekkel"""
    def shutdown_task():
        from app.database import SessionLocal
        from app.services.server_control_service import send_rcon_command
        
        shutdown_db = SessionLocal()
        try:
            server = shutdown_db.query(ServerInstance).filter(ServerInstance.id == server_id).first()
            if not server or server.status != ServerStatus.RUNNING:
                shutdown_db.close()
                return
            
            # RCON beállítások
            config = server.config or {}
            rcon_enabled = config.get("RCON_ENABLED", True)
            rcon_port = server.rcon_port or 27020
            server_admin_password = config.get("SERVER_ADMIN_PASSWORD", "")
            
            if not rcon_enabled or not server_admin_password:
                logger.warning(f"RCON nincs engedélyezve vagy nincs jelszó, shutdown chat üzenetek kihagyva")
                shutdown_db.close()
                return
            
            # Minden percnél chat üzenet (1-től minutes-ig)
            for remaining_minutes in range(minutes, 0, -1):
                # Ellenőrizzük, hogy még mindig ütemezve van-e
                with shutdown_lock:
                    if server_id not in scheduled_shutdowns:
                        logger.info(f"Shutdown törölve, kilépés")
                        shutdown_db.close()
                        return
                
                if remaining_minutes == minutes:
                    # Első üzenet
                    message = f'[SERVER] A szerver {minutes} perc múlva leáll!'
                elif remaining_minutes == 1:
                    message = '[SERVER] A szerver 1 perc múlva leáll!'
                else:
                    message = f'[SERVER] A szerver {remaining_minutes} perc múlva leáll!'
                
                # Chat üzenet küldése
                try:
                    send_rcon_command("localhost", rcon_port, server_admin_password, f'ServerChat "{message}"')
                    logger.info(f"Shutdown chat üzenet küldve: {message}")
                except Exception as e:
                    logger.warning(f"Chat üzenet küldése sikertelen: {e}")
                
                # Ha nem az utolsó perc, várunk 60 másodpercet
                if remaining_minutes > 1:
                    time.sleep(60)
            
            # 30 másodperctől másodpercenként visszaszámlálás
            for remaining_seconds in range(30, 0, -1):
                # Ellenőrizzük, hogy még mindig ütemezve van-e
                with shutdown_lock:
                    if server_id not in scheduled_shutdowns:
                        logger.info(f"Shutdown törölve, kilépés")
                        shutdown_db.close()
                        return
                
                message = f'[SERVER] Leállítás {remaining_seconds} másodperc múlva!'
                
                # Chat üzenet küldése
                try:
                    send_rcon_command("localhost", rcon_port, server_admin_password, f'ServerChat "{message}"')
                    logger.info(f"Shutdown chat üzenet küldve: {message}")
                except Exception as e:
                    logger.warning(f"Chat üzenet küldése sikertelen: {e}")
                
                time.sleep(1)
            
            # Ellenőrizzük, hogy még mindig ütemezve van-e
            with shutdown_lock:
                if server_id in scheduled_shutdowns:
                    shutdown_time = scheduled_shutdowns[server_id]
                    if datetime.now() >= shutdown_time:
                        # Leállítjuk a szervert shutdown command-dal (mint a POK-manager.sh-ben)
                        from app.services.server_control_service import check_process_running_in_container, wait_for_process_shutdown
                        container_name = f"zedin_asa_{server_id}"
                        
                        try:
                            # Ellenőrizzük, hogy a folyamat még fut-e
                            if check_process_running_in_container(container_name, "ArkAscendedServer.exe"):
                                # Végül küldjük a saveworld parancsot (mint a POK-manager.sh-ben)
                                logger.info("Végső saveworld parancs küldése...")
                                try:
                                    send_rcon_command("localhost", rcon_port, server_admin_password, "saveworld", timeout=3)
                                    time.sleep(5)  # Várunk 5 másodpercet, hogy a save befejeződjön
                                except Exception as save_error:
                                    logger.warning(f"Saveworld parancs hiba: {save_error}, folytatjuk...")
                            
                            # Shutdown parancs küldése
                            logger.info(f"Shutdown parancs küldése szerver {server_id}-re...")
                            try:
                                send_rcon_command("localhost", rcon_port, server_admin_password, "shutdown", timeout=3)
                                logger.info("Shutdown parancs elküldve, várakozás 10 másodpercet...")
                                time.sleep(10)  # Várunk 10 másodpercet, hogy a shutdown parancs feldolgozódjon
                            except Exception as shutdown_error:
                                logger.warning(f"Shutdown parancs küldése sikertelen: {shutdown_error}, folytatjuk a konténer leállításával")
                            
                            # Várjuk meg, hogy a folyamat leálljon (max 30 másodperc, nem 3 perc)
                            logger.info("Várakozás, hogy a szerver leálljon (max 30 másodperc)...")
                            process_stopped = wait_for_process_shutdown(container_name, "ArkAscendedServer.exe", max_wait_seconds=30)
                            
                            if not process_stopped:
                                logger.warning("A folyamat nem állt le 30 másodperc alatt, folytatjuk a konténer leállításával")
                            
                        except Exception as e:
                            logger.warning(f"Shutdown folyamat hiba: {e}, folytatjuk a konténer leállításával")
                        
                        # Végül mindig leállítjuk a konténert (akár működött a shutdown parancs, akár nem)
                        logger.info("Konténer leállítása...")
                        from app.services.server_control_service import stop_server
                        result = stop_server(server, shutdown_db)
                        logger.info(f"Scheduled shutdown executed for server {server_id}: {result}")
                        
                        # Töröljük az ütemezett leállítást
                        if server_id in scheduled_shutdowns:
                            del scheduled_shutdowns[server_id]
        except Exception as e:
            logger.error(f"Error executing scheduled shutdown for server {server_id}: {e}")
        finally:
            shutdown_db.close()
    
    thread = threading.Thread(target=shutdown_task, daemon=True)
    thread.start()
    return thread

@router.get("/servers/{server_id}/logs")
async def get_server_logs(
    request: Request,
    server_id: int,
    db: Session = Depends(get_db),
    log_type: str = Query("startup", description="Log típus: 'startup' vagy 'docker'")
):
    """Server Admin: Szerver logok megtekintése (indítási vagy Docker konténer logok)"""
    current_user = require_server_admin(request, db)
    
    server = db.query(ServerInstance).filter(
        and_(
            ServerInstance.id == server_id,
            ServerInstance.server_admin_id == current_user.id
        )
    ).first()
    
    if not server:
        raise HTTPException(status_code=404, detail="Szerver nem található")
    
    # Docker konténer logok lekérése
    if log_type == "docker":
        import subprocess
        from app.services.symlink_service import get_server_dedicated_saved_path, get_server_path
        
        container_name = f"zedin_asa_{server.id}"
        
        # Próbáljuk meg először a Saved/Logs mappában lévő log fájlt olvasni
        # Ez csak a szerver kimenetét tartalmazza, nem az entrypoint.sh üzeneteket
        server_path = get_server_path(server.id)
        saved_path = get_server_dedicated_saved_path(server_path)
        server_log_file = saved_path / "Logs" / "server.log"
        
        # Ha van szerver log fájl, olvassuk be azt (ez csak a szerver kimenetét tartalmazza)
        if server_log_file.exists():
            try:
                with open(server_log_file, 'r', encoding='utf-8', errors='ignore') as f:
                    # Utolsó 500 sort olvassuk be
                    lines = f.readlines()
                    last_lines = lines[-500:] if len(lines) > 500 else lines
                    server_log_content = ''.join(last_lines)
                
                # Ellenőrizzük a konténer státuszát is
                try:
                    check_result = subprocess.run(
                        ["docker", "ps", "-q", "-f", f"name=^{container_name}$"],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    container_status = "running" if check_result.stdout.strip() else "stopped"
                except:
                    container_status = "unknown"
                
                return JSONResponse({
                    "success": True,
                    "log_type": "docker",
                    "log_source": "server_log_file",
                    "container_name": container_name,
                    "container_status": container_status,
                    "log_file": str(server_log_file),
                    "log_content": server_log_content,
                    "log_lines": len(server_log_content.splitlines()),
                    "total_lines": len(lines)
                })
            except Exception as e:
                # Ha nem sikerül olvasni a log fájlt, folytatjuk a Docker logs-al
                pass
        
        # Ha nincs szerver log fájl, vagy nem sikerült olvasni, használjuk a Docker logs-ot
        try:
            # Ellenőrizzük, hogy a konténer fut-e
            check_result = subprocess.run(
                ["docker", "ps", "-q", "-f", f"name=^{container_name}$"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if not check_result.stdout.strip():
                # Ha nem fut, ellenőrizzük, hogy létezik-e
                exists_result = subprocess.run(
                    ["docker", "ps", "-a", "-q", "-f", f"name=^{container_name}$"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                if not exists_result.stdout.strip():
                    return JSONResponse({
                        "success": False,
                        "message": f"Konténer {container_name} nem található"
                    })
                else:
                    # Konténer létezik, de nem fut
                    # Több sort kérünk, hogy lássuk a szerver logokat is
                    log_result = subprocess.run(
                        ["docker", "logs", "--tail", "1000", container_name],
                        capture_output=True,
                        text=True,
                        timeout=15
                    )
                    
                    # Szűrjük a logokat: csak a szerver kimenetét mutatjuk (Commandline sor után)
                    log_lines = log_result.stdout.splitlines()
                    filtered_lines = []
                    found_commandline = False
                    
                    for line in log_lines:
                        # Ha megtaláltuk a Commandline sort, onnantól kezdve minden sor a szerver kimenete
                        if "Commandline:" in line or "[202" in line:
                            found_commandline = True
                            filtered_lines.append(line)
                        elif found_commandline:
                            # Commandline után minden sor a szerver kimenete
                            filtered_lines.append(line)
                        elif not found_commandline and any(marker in line for marker in ["[202", "Log file open", "ARK Version", "LogMemory"]):
                            # Ha még nem találtuk meg a Commandline sort, de látunk ARK szerver log sort, akkor is hozzáadjuk
                            found_commandline = True
                            filtered_lines.append(line)
                    
                    # Ha nem találtunk Commandline sort, de van log, akkor az utolsó 500 sort mutatjuk
                    if not filtered_lines and log_lines:
                        filtered_lines = log_lines[-500:]
                    
                    filtered_content = '\n'.join(filtered_lines) if filtered_lines else log_result.stdout
                    
                    return JSONResponse({
                        "success": True,
                        "log_type": "docker",
                        "log_source": "docker_logs",
                        "container_name": container_name,
                        "container_status": "stopped",
                        "log_content": filtered_content,
                        "log_lines": len(filtered_lines),
                        "original_lines": len(log_lines),
                        "filtered": len(filtered_lines) < len(log_lines)
                    })
            
            # Konténer fut, logok lekérése
            # Több sort kérünk, hogy lássuk a szerver logokat is (az entrypoint.sh üzenetek után)
            log_result = subprocess.run(
                ["docker", "logs", "--tail", "1000", container_name],
                capture_output=True,
                text=True,
                timeout=15
            )
            
            if log_result.returncode != 0:
                return JSONResponse({
                    "success": False,
                    "message": f"Docker logok lekérése sikertelen: {log_result.stderr}"
                })
            
            # Szűrjük a logokat: csak a szerver kimenetét mutatjuk (Commandline sor után)
            log_lines = log_result.stdout.splitlines()
            filtered_lines = []
            found_commandline = False
            
            for line in log_lines:
                # Ha megtaláltuk a Commandline sort, onnantól kezdve minden sor a szerver kimenete
                if "Commandline:" in line or "[202" in line:
                    found_commandline = True
                    filtered_lines.append(line)
                elif found_commandline:
                    # Commandline után minden sor a szerver kimenete
                    filtered_lines.append(line)
                elif not found_commandline and any(marker in line for marker in ["[202", "Log file open", "ARK Version", "LogMemory"]):
                    # Ha még nem találtuk meg a Commandline sort, de látunk ARK szerver log sort, akkor is hozzáadjuk
                    found_commandline = True
                    filtered_lines.append(line)
            
            # Ha nem találtunk Commandline sort, de van log, akkor az utolsó 500 sort mutatjuk
            if not filtered_lines and log_lines:
                filtered_lines = log_lines[-500:]
            
            filtered_content = '\n'.join(filtered_lines) if filtered_lines else log_result.stdout
            
            return JSONResponse({
                "success": True,
                "log_type": "docker",
                "log_source": "docker_logs",
                "container_name": container_name,
                "container_status": "running",
                "log_content": filtered_content,
                "log_lines": len(filtered_lines),
                "original_lines": len(log_lines),
                "filtered": len(filtered_lines) < len(log_lines)
            })
            
        except subprocess.TimeoutExpired:
            return JSONResponse({
                "success": False,
                "message": "Docker logok lekérése túllépte az időkorlátot"
            })
        except Exception as e:
            return JSONResponse({
                "success": False,
                "message": f"Docker logok lekérése sikertelen: {str(e)}"
            })
    
    # Indítási logok (alapértelmezett)
    from app.services.symlink_service import get_server_path
    server_path = get_server_path(server.id)
    
    # Legutóbbi log fájl keresése
    log_files = sorted(server_path.glob("startup_log_*.txt"), key=lambda x: x.stat().st_mtime, reverse=True)
    
    if not log_files:
        return JSONResponse({
            "success": False,
            "message": "Nincs indítási log fájl"
        })
    
    latest_log = log_files[0]
    
    try:
        with open(latest_log, 'r', encoding='utf-8') as f:
            log_content = f.read()
        
        return JSONResponse({
            "success": True,
            "log_type": "startup",
            "log_file": latest_log.name,
            "log_content": log_content,
            "file_size": latest_log.stat().st_size
        })
    except Exception as e:
        return JSONResponse({
            "success": False,
            "message": f"Log fájl olvasása sikertelen: {str(e)}"
        })

@router.get("/servers/{server_id}/logs/page", response_class=HTMLResponse)
async def server_logs_page(
    request: Request,
    server_id: int,
    db: Session = Depends(get_db),
    log_file: str = Query(None, description="Kiválasztott log fájl neve")
):
    """Server Admin: Szerver logok oldal - log fájlok listázása és megjelenítése"""
    current_user = require_server_admin(request, db)
    
    server = db.query(ServerInstance).filter(
        and_(
            ServerInstance.id == server_id,
            ServerInstance.server_admin_id == current_user.id
        )
    ).first()
    
    if not server:
        raise HTTPException(status_code=404, detail="Szerver nem található")
    
    from app.services.symlink_service import get_server_path
    server_path = get_server_path(server.id)
    
    # Log fájlok listázása - csak ShooterGame.log
    log_files = []
    
    # Saved/Logs könyvtárban csak ShooterGame.log
    saved_logs_dir = server_path / "Saved" / "Logs"
    if saved_logs_dir.exists():
        shooter_game_log = saved_logs_dir / "ShooterGame.log"
        if shooter_game_log.exists():
            log_files.append({
                "name": shooter_game_log.name,
                "path": str(shooter_game_log),
                "size": shooter_game_log.stat().st_size,
                "modified": datetime.fromtimestamp(shooter_game_log.stat().st_mtime),
                "type": "server"
            })
    
    # Kiválasztott log fájl tartalma (ha nincs kiválasztva, automatikusan a ShooterGame.log)
    selected_log_content = None
    selected_log_name = None
    
    # Ha nincs kiválasztott fájl, automatikusan a ShooterGame.log-t jelenítjük meg
    if not log_file and log_files:
        log_file = log_files[0]["name"]
    
    if log_file:
        # Keresés a log fájlok között
        for log_info in log_files:
            if log_info["name"] == log_file:
                try:
                    with open(log_info["path"], 'r', encoding='utf-8', errors='ignore') as f:
                        selected_log_content = f.read()
                    selected_log_name = log_info["name"]
                    break
                except Exception as e:
                    logger.error(f"Log fájl olvasása sikertelen: {e}")
                    break
    
    # Docker konténer logok (ha fut a szerver)
    container_name = f"ark-server-{server.id}"
    docker_logs_available = False
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", f"name={container_name}", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=5
        )
        docker_logs_available = container_name in result.stdout
    except:
        pass
    
    return templates.TemplateResponse(
        "ark/server_logs.html",
        {
            "request": request,
            "server": server,
            "log_files": log_files,
            "selected_log_content": selected_log_content,
            "selected_log_name": selected_log_name,
            "docker_logs_available": docker_logs_available
        }
    )

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
    server_admin_password: str = Form(...),  # Kötelező
    server_password: str = Form(None),
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
    
    # Admin jelszó kötelező
    if server_admin_password and server_admin_password.strip():
        server_config["ServerAdminPassword"] = server_admin_password.strip()
    else:
        raise HTTPException(
            status_code=400,
            detail="Szerver Admin Jelszó kötelező! Kérlek add meg az admin jelszót."
        )
    
    # Szerver jelszó (opcionális)
    if server_password and server_password.strip():
        server_config["ServerPassword"] = server_password.strip()
    
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
                create_docker_compose_file(server_instance, serverfiles_link, saved_path, db)
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

@router.get("/servers/{server_id}/rcon/status")
async def get_rcon_status(
    request: Request,
    server_id: int,
    db: Session = Depends(get_db)
):
    """Server Admin: RCON kapcsolat státusza"""
    current_user = require_server_admin(request, db)
    
    server = db.query(ServerInstance).filter(
        and_(
            ServerInstance.id == server_id,
            ServerInstance.server_admin_id == current_user.id
        )
    ).first()
    
    if not server:
        raise HTTPException(status_code=404, detail="Szerver nem található")
    
    # RCON beállítások
    config = server.config or {}
    rcon_enabled = config.get("RCON_ENABLED", True)
    rcon_port = server.rcon_port or 27020
    server_admin_password = config.get("SERVER_ADMIN_PASSWORD", "")
    
    if not rcon_enabled:
        return JSONResponse({
            "success": True,
            "rcon_enabled": False,
            "rcon_working": False,
            "message": "RCON nincs engedélyezve"
        })
    
    if not server_admin_password:
        return JSONResponse({
            "success": True,
            "rcon_enabled": True,
            "rcon_working": False,
            "message": "RCON jelszó nincs beállítva"
        })
    
    # RCON kapcsolat tesztelése
    from app.services.server_control_service import test_rcon_connection
    rcon_working = test_rcon_connection("localhost", rcon_port, server_admin_password, timeout=3)
    
    return JSONResponse({
        "success": True,
        "rcon_enabled": True,
        "rcon_working": rcon_working,
        "rcon_port": rcon_port,
        "message": "RCON működik" if rcon_working else "RCON nem elérhető"
    })

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
        # Automatikusan leállítjuk a szervert
        try:
            from app.services.server_control_service import stop_server
            stop_result = stop_server(server, db)
            if not stop_result.get("success"):
                return RedirectResponse(
                    url=f"/ark/servers?error=A+szerver+leállítása+sikertelen.+Kérem,+állítsa+le+manuálisan",
                    status_code=302
                )
            # Várunk egy kicsit, hogy a konténer biztosan leálljon
            import time
            time.sleep(2)
        except Exception as e:
            print(f"Figyelmeztetés: Szerver automatikus leállítása sikertelen: {e}")
            return RedirectResponse(
                url=f"/ark/servers?error=A+szerver+törlése+előtt+először+le+kell+állítani",
                status_code=302
            )
    
    # Docker konténer leállítása és törlése (ha még fut)
    try:
        import subprocess
        container_name = f"zedin_asa_{server.id}"
        # Ellenőrizzük, hogy a konténer fut-e
        result = subprocess.run(
            ["docker", "ps", "-a", "-q", "-f", f"name=^{container_name}$"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            # Konténer leállítása és törlése
            subprocess.run(
                ["docker", "stop", container_name],
                capture_output=True,
                timeout=10
            )
            subprocess.run(
                ["docker", "rm", container_name],
                capture_output=True,
                timeout=10
            )
            print(f"Docker konténer leállítva és törölve: {container_name}")
    except Exception as e:
        print(f"Figyelmeztetés: Docker konténer törlése sikertelen: {e}")
    
    # Instance mappa törlése (Docker Compose fájlokkal együtt) - ELŐSZÖR
    # Ezt előbb töröljük, hogy a fájlok ne legyenek lock-olva
    try:
        from app.services.server_control_service import remove_instance_dir
        remove_instance_dir(server.id)
    except Exception as e:
        # Ha hiba van, csak logoljuk, de ne akadályozza a törlést
        print(f"Figyelmeztetés: Instance mappa törlése sikertelen: {e}")
    
    # Symlink eltávolítása és Saved mappa törlése (ha létezik)
    try:
        cluster = db.query(Cluster).filter(Cluster.id == server.cluster_id).first() if server.cluster_id else None
        cluster_id_str = cluster.cluster_id if cluster else None
        remove_server_symlink(server.id, cluster_id_str)
    except Exception as e:
        # Ha hiba van, csak logoljuk, de ne akadályozza a törlést
        print(f"Figyelmeztetés: Symlink és Saved mappa törlése sikertelen: {e}")
    
    # Szerver törlése az adatbázisból (előbb, hogy ellenőrizhessük, van-e még más szerver)
    user_id = server.server_admin_id
    
    # Ellenőrizzük, hogy van-e még más szerver, ami ezt a felhasználót használja (MEGELŐZŐLEG)
    remaining_servers = db.query(ServerInstance).filter(
        ServerInstance.server_admin_id == user_id
    ).count()
    
    print(f"DEBUG: Felhasználó {user_id} szervereinek száma törlés előtt: {remaining_servers}")
    
    # Szerver törlése az adatbázisból
    db.delete(server)
    db.commit()
    
    # Ellenőrizzük újra, hogy van-e még más szerver
    remaining_servers_after = db.query(ServerInstance).filter(
        ServerInstance.server_admin_id == user_id
    ).count()
    
    print(f"DEBUG: Felhasználó {user_id} szervereinek száma törlés után: {remaining_servers_after}")
    
    # MINDENKÉPPEN töröljük a ServerFiles/user_{user_id} mappát (függetlenül attól, hogy van-e más szerver)
    try:
        from app.services.symlink_service import get_user_serverfiles_path
        import shutil
        import logging
        import stat
        import os
        logger = logging.getLogger(__name__)
        
        user_serverfiles_path = get_user_serverfiles_path(user_id)
        print(f"DEBUG: ServerFiles mappa útvonal: {user_serverfiles_path}")
        print(f"DEBUG: ServerFiles mappa létezik: {user_serverfiles_path.exists()}")
        
        if user_serverfiles_path.exists():
            # Először javítjuk a jogosultságokat (ha szükséges)
            try:
                current_uid = os.getuid()
                current_gid = os.getgid()
                # Jogosultságok javítása rekurzívan
                for root, dirs, files in os.walk(user_serverfiles_path):
                    for d in dirs:
                        try:
                            dir_path = os.path.join(root, d)
                            os.chmod(dir_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
                            if os.name != 'nt':
                                os.chown(dir_path, current_uid, current_gid)
                        except (PermissionError, OSError):
                            pass
                    for f in files:
                        try:
                            file_path = os.path.join(root, f)
                            os.chmod(file_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
                            if os.name != 'nt':
                                os.chown(file_path, current_uid, current_gid)
                        except (PermissionError, OSError):
                            pass
            except Exception as perm_e:
                print(f"Figyelmeztetés: Jogosultságok javítása sikertelen: {perm_e}")
            
            # Most próbáljuk meg törölni
            try:
                shutil.rmtree(user_serverfiles_path)
                print(f"✓ ServerFiles/user_{user_id} mappa sikeresen törölve: {user_serverfiles_path}")
                logger.info(f"ServerFiles/user_{user_id} mappa törölve: {user_serverfiles_path}")
            except PermissionError as pe:
                print(f"✗ Jogosultsági hiba a ServerFiles/user_{user_id} mappa törlésekor: {pe}")
                logger.error(f"Jogosultsági hiba a ServerFiles/user_{user_id} mappa törlésekor: {pe}")
                # Próbáljuk meg fájlonként törölni (ha a teljes mappa nem törölhető)
                try:
                    # Próbáljuk meg átnevezni (ha törölni nem lehet)
                    backup_path = user_serverfiles_path.parent / f"user_{user_id}.deleted"
                    if backup_path.exists():
                        shutil.rmtree(backup_path)
                    user_serverfiles_path.rename(backup_path)
                    print(f"✓ ServerFiles/user_{user_id} mappa átnevezve (törlés helyett): {backup_path}")
                    logger.info(f"ServerFiles/user_{user_id} mappa átnevezve: {backup_path}")
                except Exception as rename_e:
                    print(f"✗ ServerFiles/user_{user_id} mappa átnevezése is sikertelen: {rename_e}")
                    logger.error(f"ServerFiles/user_{user_id} mappa átnevezése sikertelen: {rename_e}")
            except Exception as e:
                print(f"✗ ServerFiles/user_{user_id} mappa törlése sikertelen: {e}")
                logger.error(f"ServerFiles/user_{user_id} mappa törlése sikertelen: {e}")
                import traceback
                traceback.print_exc()
        else:
            print(f"INFO: ServerFiles/user_{user_id} mappa nem létezik: {user_serverfiles_path}")
    except Exception as e:
        # Ha hiba van, csak logoljuk, de ne akadályozza a törlést
        print(f"✗ Figyelmeztetés: ServerFiles/user_{user_id} mappa törlése sikertelen: {e}")
        import traceback
        traceback.print_exc()
    else:
        print(f"INFO: Még van {remaining_servers_after} szerver a felhasználónak, ServerFiles mappa megtartva")
    
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
    # FONTOS: A két jelszó teljesen független egymástól:
    # - ServerAdminPassword: RCON és admin parancsokhoz használt jelszó (ingame admin) - KÖTELEZŐ
    # - ServerPassword: A szerver jelszava, amit a játékosoknak kell megadniuk, hogy csatlakozzanak
    # Nincs ellenőrzés, hogy a két jelszó különböző legyen - lehet ugyanaz is.
    # Admin jelszó kötelező - ha nincs megadva új érték, akkor a meglévőt használjuk, de legalább egynek lennie kell
    if server_admin_password and server_admin_password.strip():
        server_config["ServerAdminPassword"] = server_admin_password
    elif not server_config.get("ServerAdminPassword"):
        # Ha nincs új érték és nincs meglévő sem, akkor hiba
        raise HTTPException(
            status_code=400,
            detail="Szerver Admin Jelszó kötelező! Kérlek add meg az admin jelszót."
        )
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
        saved_path = server_path / "Saved"
        
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
            
            # Docker Compose fájl és indítási parancs fájl frissítése, hogy az új beállítások tükröződjenek
            if saved_path.exists():
                try:
                    from app.services.server_control_service import create_docker_compose_file
                    create_docker_compose_file(server, serverfiles_link, saved_path, db)
                    print(f"Docker Compose és indítási parancs fájl frissítve szerver szerkesztésekor: {server.id}")
                except Exception as e:
                    print(f"Figyelmeztetés: Docker Compose fájl frissítése sikertelen: {e}")
                    import traceback
                    traceback.print_exc()
    
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

@router.post("/servers/{server_id}/shutdown")
async def schedule_shutdown(
    request: Request,
    server_id: int,
    db: Session = Depends(get_db)
):
    """Server Admin: Késleltetett leállítás beállítása"""
    current_user = require_server_admin(request, db)
    
    server = db.query(ServerInstance).filter(
        and_(
            ServerInstance.id == server_id,
            ServerInstance.server_admin_id == current_user.id
        )
    ).first()
    
    if not server:
        raise HTTPException(status_code=404, detail="Szerver nem található")
    
    if server.status != ServerStatus.RUNNING:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "A szerver nem fut"}
        )
    
    # JSON body olvasása
    try:
        body = await request.json()
        minutes = int(body.get("minutes", 5))
    except:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Érvénytelen kérés"}
        )
    
    if minutes < 1 or minutes > 60:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "A perc értéknek 1-60 között kell lennie"}
        )
    
    # Ütemezett leállítás beállítása
    shutdown_time = datetime.now() + timedelta(minutes=minutes)
    
    with shutdown_lock:
        # Ha már van ütemezett leállítás, töröljük
        if server_id in scheduled_shutdowns:
            # Megjegyzés: a régi thread továbbra is futhat, de az ellenőrzi a scheduled_shutdowns dict-et
            pass
        scheduled_shutdowns[server_id] = shutdown_time
    
    # Háttérfolyamat indítása
    schedule_server_shutdown(server_id, minutes, db)
    
    logger.info(f"Scheduled shutdown for server {server_id} in {minutes} minutes")
    
    return JSONResponse(
        content={
            "success": True,
            "message": f"Leállítás ütemezve {minutes} percre",
            "shutdown_time": shutdown_time.isoformat()
        }
    )

@router.post("/servers/{server_id}/shutdown/cancel")
async def cancel_shutdown(
    request: Request,
    server_id: int,
    db: Session = Depends(get_db)
):
    """Server Admin: Ütemezett leállítás törlése"""
    current_user = require_server_admin(request, db)
    
    server = db.query(ServerInstance).filter(
        and_(
            ServerInstance.id == server_id,
            ServerInstance.server_admin_id == current_user.id
        )
    ).first()
    
    if not server:
        raise HTTPException(status_code=404, detail="Szerver nem található")
    
    with shutdown_lock:
        if server_id in scheduled_shutdowns:
            del scheduled_shutdowns[server_id]
            logger.info(f"Cancelled scheduled shutdown for server {server_id}")
            return JSONResponse(
                content={"success": True, "message": "Ütemezett leállítás törölve"}
            )
        else:
            return JSONResponse(
                content={"success": False, "message": "Nincs ütemezett leállítás"}
            )

@router.get("/servers/{server_id}/shutdown/status")
async def get_shutdown_status(
    request: Request,
    server_id: int,
    db: Session = Depends(get_db)
):
    """Server Admin: Ütemezett leállítás státusza"""
    current_user = require_server_admin(request, db)
    
    server = db.query(ServerInstance).filter(
        and_(
            ServerInstance.id == server_id,
            ServerInstance.server_admin_id == current_user.id
        )
    ).first()
    
    if not server:
        raise HTTPException(status_code=404, detail="Szerver nem található")
    
    with shutdown_lock:
        if server_id in scheduled_shutdowns:
            shutdown_time = scheduled_shutdowns[server_id]
            return JSONResponse(
                content={
                    "success": True,
                    "scheduled": True,
                    "shutdown_time": shutdown_time.isoformat()
                }
            )
        else:
            return JSONResponse(
                content={
                    "success": True,
                    "scheduled": False
                }
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
            create_docker_compose_file(server, serverfiles_link, saved_path, db)
            # Szerver újraindítása, hogy a memória limit életbe lépjen
            from app.services.server_control_service import restart_server
            restart_server(server, db)
    
    return RedirectResponse(
        url=f"/ark/servers?success=RAM+limit+beállítva",
        status_code=302
    )


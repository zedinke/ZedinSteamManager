"""
Szerver indítási/leállítási/restart szolgáltatás
"""

import subprocess
import os
import signal
import psutil
from pathlib import Path
from typing import Optional, Dict
from sqlalchemy.orm import Session
from app.database import ServerInstance, ServerStatus
from app.services.symlink_service import get_server_path, get_active_user_serverfiles, get_active_ark_files
from app.config import settings
import json
import logging

logger = logging.getLogger(__name__)

def find_server_executable(server_path: Path) -> Optional[Path]:
    """
    Ark szerver executable fájl keresése
    
    Args:
        server_path: Szerver útvonal (symlink vagy valós mappa)
    
    Returns:
        Path objektum az executable fájlhoz vagy None
    """
    # Ha symlink, követjük a valós útvonalat
    real_path = server_path
    if server_path.is_symlink():
        try:
            real_path = server_path.resolve()
        except Exception as e:
            logger.warning(f"Symlink követése sikertelen: {e}")
            real_path = server_path
    
    # Windows: ShooterGameServer.exe
    # Linux: ShooterGameServer
    possible_names = ["ShooterGameServer.exe", "ShooterGameServer"]
    
    # Lehetséges útvonalak
    possible_paths = [
        # Standard Ark Survival Ascended struktúra
        real_path / "ShooterGame" / "Binaries" / "Win64",
        real_path / "ShooterGame" / "Binaries" / "Linux",
        # Alternatív struktúrák
        real_path / "Binaries" / "Win64",
        real_path / "Binaries" / "Linux",
        # Közvetlenül a szerver mappában
        real_path,
    ]
    
    # Keresés minden lehetséges útvonalon
    for base_path in possible_paths:
        if not base_path.exists():
            continue
        
        for name in possible_names:
            exe_path = base_path / name
            if exe_path.exists() and exe_path.is_file():
                logger.info(f"Executable található: {exe_path}")
                return exe_path
    
    # Ha nem találtuk, próbáljuk meg rekurzívan keresni
    logger.warning(f"Executable nem található a szabványos útvonalakon, rekurzív keresés...")
    for name in possible_names:
        for exe_path in real_path.rglob(name):
            if exe_path.is_file():
                logger.info(f"Executable található rekurzív kereséssel: {exe_path}")
                return exe_path
    
    logger.error(f"Executable nem található a következő útvonalon: {real_path}")
    return None

def build_start_command(server: ServerInstance, server_path: Path, exe_path: Path) -> list:
    """
    Szerver indítási parancs összeállítása
    
    Args:
        server: ServerInstance objektum
        server_path: Szerver útvonal
        exe_path: Executable fájl útvonala
    
    Returns:
        Lista a parancs argumentumokkal
    """
    config = server.config or {}
    
    # Alap parancs
    cmd = [str(exe_path)]
    
    # Map név
    map_name = config.get("MAP_NAME", "TheIsland")
    cmd.append(map_name)
    
    # Query string paraméterek összeállítása
    query_params = []
    
    # Port
    if server.port:
        query_params.append(f"Port={server.port}")
    
    # Query Port
    if server.query_port:
        query_params.append(f"QueryPort={server.query_port}")
    
    # Session Name
    session_name = config.get("SESSION_NAME", server.name)
    if session_name:
        # Session name-ben lehetnek szóközök, ezeket escape-eljük
        session_name_escaped = session_name.replace(" ", "%20")
        query_params.append(f"SessionName={session_name_escaped}")
    
    # Server Admin Password
    server_admin_password = config.get("ServerAdminPassword")
    if server_admin_password:
        query_params.append(f"ServerAdminPassword={server_admin_password}")
    
    # Server Password
    server_password = config.get("ServerPassword")
    if server_password:
        query_params.append(f"ServerPassword={server_password}")
    
    # Max Players
    if server.max_players:
        query_params.append(f"MaxPlayers={server.max_players}")
    
    # RCON Enabled
    rcon_enabled = config.get("RCON_ENABLED", True)
    if rcon_enabled and server.rcon_port:
        query_params.append(f"RCONEnabled=True")
        query_params.append(f"RCONPort={server.rcon_port}")
    
    # Active Mods
    if server.active_mods:
        mods_str = ",".join(str(mod_id) for mod_id in server.active_mods)
        query_params.append(f"ActiveMods={mods_str}")
    
    # Passive Mods
    if server.passive_mods:
        mods_str = ",".join(str(mod_id) for mod_id in server.passive_mods)
        query_params.append(f"PassiveMods={mods_str}")
    
    # Query string hozzáadása
    if query_params:
        query_string = "?" + "&".join(query_params)
        cmd.append(query_string)
    
    # BattleEye
    battleeye = config.get("BATTLEEYE", False)
    if battleeye:
        cmd.append("-UseBattlEye")
    else:
        cmd.append("-NoBattlEye")
    
    # API
    api = config.get("API", False)
    if api:
        cmd.append("-UseServerApi")
    
    # Custom Server Args
    custom_args = config.get("CUSTOM_SERVER_ARGS", "")
    if custom_args:
        # Parse custom args (space-separated)
        custom_args_list = custom_args.split()
        cmd.extend(custom_args_list)
    
    # Logging
    cmd.append("-log")
    
    return cmd

def get_start_command_string(server: ServerInstance, db: Session) -> Optional[str]:
    """
    Szerver indítási parancs string formában (megjelenítéshez)
    
    Args:
        server: ServerInstance objektum
        db: Database session
    
    Returns:
        String formában a parancs vagy None
    """
    try:
        # Szerver útvonal lekérése
        if server.server_path:
            server_path = Path(server.server_path)
        else:
            from app.database import Cluster
            cluster = db.query(Cluster).filter(Cluster.id == server.cluster_id).first() if server.cluster_id else None
            cluster_id_str = cluster.cluster_id if cluster else None
            server_path = get_server_path(server.id, cluster_id_str, server.server_admin_id)
        
        if not server_path or not server_path.exists():
            return None
        
        # Executable keresése
        exe_path = find_server_executable(server_path)
        if not exe_path:
            return None
        
        # Parancs összeállítása
        cmd = build_start_command(server, server_path, exe_path)
        
        # String formába konvertálás
        return " ".join(f'"{arg}"' if " " in arg else arg for arg in cmd)
    except Exception as e:
        logger.error(f"Hiba a parancs generálásakor: {e}")
        return None

def get_server_process(server: ServerInstance) -> Optional[psutil.Process]:
    """
    Szerver folyamat keresése
    
    Args:
        server: ServerInstance objektum
    
    Returns:
        psutil.Process objektum vagy None
    """
    try:
        # Port alapján keresünk
        if not server.port:
            return None
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.info.get('cmdline', [])
                if not cmdline:
                    continue
                
                # Ellenőrizzük, hogy tartalmazza-e a portot
                cmdline_str = " ".join(cmdline)
                if str(server.port) in cmdline_str and ("ShooterGameServer" in cmdline_str or "ShooterGame" in cmdline_str):
                    return proc
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception as e:
        logger.error(f"Hiba a folyamat keresésekor: {e}")
    
    return None

def start_server(server: ServerInstance, db: Session) -> Dict[str, any]:
    """
    Szerver indítása
    
    Args:
        server: ServerInstance objektum
        db: Database session
    
    Returns:
        Dict az eredménnyel
    """
    try:
        # Ellenőrizzük, hogy már fut-e
        if server.status == ServerStatus.RUNNING:
            proc = get_server_process(server)
            if proc and proc.is_running():
                return {
                    "success": False,
                    "message": "A szerver már fut"
                }
        
        # Szerver útvonal lekérése
        if server.server_path:
            server_path = Path(server.server_path)
        else:
            from app.database import Cluster
            cluster = db.query(Cluster).filter(Cluster.id == server.cluster_id).first() if server.cluster_id else None
            cluster_id_str = cluster.cluster_id if cluster else None
            server_path = get_server_path(server.id, cluster_id_str, server.server_admin_id)
        
        if not server_path or not server_path.exists():
            return {
                "success": False,
                "message": "Szerver útvonal nem található"
            }
        
        # Executable keresése
        exe_path = find_server_executable(server_path)
        if not exe_path:
            # Részletes hibaüzenet
            real_path = server_path.resolve() if server_path.is_symlink() else server_path
            logger.error(f"Executable nem található. Szerver útvonal: {server_path}, Valós útvonal: {real_path}")
            
            # Ellenőrizzük, hogy létezik-e a szerver útvonal
            if not server_path.exists():
                return {
                    "success": False,
                    "message": f"Szerver útvonal nem létezik: {server_path}"
                }
            
            # Ellenőrizzük, hogy a symlink helyes-e
            if server_path.is_symlink():
                try:
                    target = server_path.readlink()
                    return {
                        "success": False,
                        "message": f"Szerver executable nem található. Symlink cél: {target}, Valós útvonal: {real_path}. Ellenőrizd, hogy az Ark szerverfájlok telepítve vannak-e."
                    }
                except Exception as e:
                    return {
                        "success": False,
                        "message": f"Symlink olvasása sikertelen: {e}"
                    }
            
            return {
                "success": False,
                "message": f"Szerver executable nem található az útvonalon: {real_path}. Ellenőrizd, hogy a ShooterGameServer.exe vagy ShooterGameServer fájl létezik-e."
            }
        
        # Parancs összeállítása
        cmd = build_start_command(server, server_path, exe_path)
        
        # Working directory beállítása
        working_dir = exe_path.parent
        
        # Szerver indítása
        process = subprocess.Popen(
            cmd,
            cwd=str(working_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
        )
        
        # Státusz frissítése
        server.status = ServerStatus.RUNNING
        from datetime import datetime
        server.started_at = datetime.now()
        db.commit()
        
        logger.info(f"Szerver {server.id} indítva, PID: {process.pid}")
        
        return {
            "success": True,
            "message": "Szerver sikeresen elindítva",
            "pid": process.pid
        }
    except Exception as e:
        logger.error(f"Hiba a szerver indításakor: {e}")
        return {
            "success": False,
            "message": f"Hiba a szerver indításakor: {str(e)}"
        }

def stop_server(server: ServerInstance, db: Session) -> Dict[str, any]:
    """
    Szerver leállítása
    
    Args:
        server: ServerInstance objektum
        db: Database session
    
    Returns:
        Dict az eredménnyel
    """
    try:
        # Folyamat keresése
        proc = get_server_process(server)
        
        if not proc or not proc.is_running():
            # Ha nem fut, akkor csak frissítjük a státuszt
            server.status = ServerStatus.STOPPED
            server.started_at = None
            db.commit()
            return {
                "success": True,
                "message": "A szerver nem futott"
            }
        
        # Folyamat leállítása
        try:
            if os.name == 'nt':  # Windows
                proc.terminate()
            else:  # Linux/Unix
                proc.send_signal(signal.SIGTERM)
            
            # Várakozás a leállásra (max 10 másodperc)
            try:
                proc.wait(timeout=10)
            except psutil.TimeoutExpired:
                # Ha nem állt le, erőszakkal leállítjuk
                proc.kill()
                proc.wait()
        except psutil.NoSuchProcess:
            pass  # Már leállt
        
        # Státusz frissítése
        server.status = ServerStatus.STOPPED
        server.started_at = None
        db.commit()
        
        logger.info(f"Szerver {server.id} leállítva")
        
        return {
            "success": True,
            "message": "Szerver sikeresen leállítva"
        }
    except Exception as e:
        logger.error(f"Hiba a szerver leállításakor: {e}")
        return {
            "success": False,
            "message": f"Hiba a szerver leállításakor: {str(e)}"
        }

def restart_server(server: ServerInstance, db: Session) -> Dict[str, any]:
    """
    Szerver újraindítása
    
    Args:
        server: ServerInstance objektum
        db: Database session
    
    Returns:
        Dict az eredménnyel
    """
    try:
        # Először leállítjuk
        stop_result = stop_server(server, db)
        if not stop_result["success"]:
            return stop_result
        
        # Várakozás (2 másodperc)
        import time
        time.sleep(2)
        
        # Újraindítás
        start_result = start_server(server, db)
        return start_result
    except Exception as e:
        logger.error(f"Hiba a szerver újraindításakor: {e}")
        return {
            "success": False,
            "message": f"Hiba a szerver újraindításakor: {str(e)}"
        }


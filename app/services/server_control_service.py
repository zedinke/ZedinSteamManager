"""
Szerver indítási/leállítási/restart szolgáltatás - Docker támogatással
"""

import subprocess
import os
import signal
import psutil
import shutil
from pathlib import Path
from typing import Optional, Dict
from sqlalchemy.orm import Session
from app.database import ServerInstance, ServerStatus
from app.services.symlink_service import get_server_path, get_server_dedicated_saved_path
from app.config import settings
import json
import logging
import yaml

logger = logging.getLogger(__name__)

def check_docker_available() -> bool:
    """
    Ellenőrzi, hogy Docker elérhető-e
    
    Returns:
        True ha Docker elérhető, False egyébként
    """
    try:
        result = subprocess.run(
            ["docker", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False

def check_docker_compose_available() -> bool:
    """
    Ellenőrzi, hogy Docker Compose elérhető-e
    
    Returns:
        True ha Docker Compose elérhető, False egyébként
    """
    # Próbáljuk meg a 'docker compose' parancsot (V2)
    try:
        result = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    
    # Próbáljuk meg a 'docker-compose' parancsot (V1)
    try:
        result = subprocess.run(
            ["docker-compose", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False

def get_docker_compose_cmd() -> Optional[str]:
    """
    Docker Compose parancs meghatározása
    
    Returns:
        'docker compose' vagy 'docker-compose' vagy None
    """
    # Próbáljuk meg a 'docker compose' parancsot (V2)
    try:
        result = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return "docker compose"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    
    # Próbáljuk meg a 'docker-compose' parancsot (V1)
    try:
        result = subprocess.run(
            ["docker-compose", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return "docker-compose"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    
    return None

def get_instance_dir(server: ServerInstance) -> Path:
    """
    Instance mappa útvonala (új struktúra: Servers/server_{server_id}/)
    A docker-compose.yaml közvetlenül a szerver mappájában van
    
    Args:
        server: ServerInstance objektum
    
    Returns:
        Path objektum a szerver mappához (ahol a docker-compose.yaml van)
    """
    # Új struktúra: Servers/server_{server_id}/
    from app.services.symlink_service import get_servers_base_path
    servers_base = get_servers_base_path()
    instance_dir = servers_base / f"server_{server.id}"
    logger.info(f"Instance mappa útvonal: {instance_dir}")
    return instance_dir

def get_instance_dir_by_id(server_id: int) -> Path:
    """
    Instance mappa útvonala szerver ID alapján (törléshez)
    Új struktúra: Servers/server_{server_id}/
    
    Args:
        server_id: Szerver ID
    
    Returns:
        Path objektum a szerver mappához
    """
    from app.services.symlink_service import get_servers_base_path
    servers_base = get_servers_base_path()
    instance_dir = servers_base / f"server_{server_id}"
    return instance_dir

def remove_instance_dir(server_id: int) -> bool:
    """
    Instance mappa törlése (Docker Compose fájlokkal együtt)
    
    Args:
        server_id: Szerver ID
    
    Returns:
        True ha sikeres, False egyébként
    """
    try:
        instance_dir = get_instance_dir_by_id(server_id)
        
        if instance_dir.exists():
            shutil.rmtree(instance_dir)
            logger.info(f"Instance mappa törölve: {instance_dir}")
            return True
        else:
            logger.info(f"Instance mappa nem létezik: {instance_dir}")
            return True  # Nincs mit törölni, de ez nem hiba
        
    except Exception as e:
        logger.error(f"Hiba az Instance mappa törlésekor: {e}")
        import traceback
        traceback.print_exc()
        return False

def get_docker_compose_file(server: ServerInstance) -> Path:
    """
    Docker Compose fájl útvonala (új struktúra: Servers/server_{server_id}/docker-compose.yaml)
    
    Args:
        server: ServerInstance objektum
    
    Returns:
        Path objektum a docker-compose fájlhoz
    """
    instance_dir = get_instance_dir(server)
    return instance_dir / "docker-compose.yaml"

def create_docker_compose_file(server: ServerInstance, serverfiles_link: Path, saved_path: Path) -> bool:
    """
    Docker Compose fájl létrehozása (új struktúra: Servers/server_{server_id}/docker-compose.yaml)
    
    Args:
        server: ServerInstance objektum
        serverfiles_link: ServerFiles symlink útvonala (Servers/server_{server_id}/ServerFiles)
        saved_path: Dedikált Saved mappa útvonala (Servers/server_{server_id}/Saved/)
    
    Returns:
        True ha sikeres, False egyébként
    """
    try:
        instance_dir = get_instance_dir(server)  # Servers/server_{server_id}/
        instance_dir.mkdir(parents=True, exist_ok=True)
        
        # Ha a saved_path egy symlink, követjük
        if saved_path.is_symlink():
            try:
                saved_path = saved_path.resolve()
            except Exception as e:
                logger.warning(f"Symlink követése sikertelen: {e}")
        
        # Ha a serverfiles_link egy symlink, követjük
        real_server_path = serverfiles_link
        if serverfiles_link.is_symlink():
            try:
                real_server_path = serverfiles_link.resolve()
            except Exception as e:
                logger.warning(f"Symlink követése sikertelen: {e}")
        
        # Docker Compose fájl útvonala
        compose_file = get_docker_compose_file(server)
        
        # Konfiguráció
        config = server.config or {}
        
        # Portok
        port = server.port or settings.ark_default_port
        query_port = server.query_port or (port + 2)
        rcon_port = server.rcon_port or settings.ark_default_rcon_port
        
        # Docker Compose YAML összeállítása
        compose_data = {
            'version': '3.8',
            'services': {
                f'asa_{server.id}': {
                    'image': 'acekorneya/asa_server:2_1_latest',
                    'container_name': f'asa_{server.id}',
                    'restart': 'unless-stopped',
                    'ports': [
                        f'{port}:{port}/tcp',
                        f'{port}:{port}/udp',
                        f'{rcon_port}:{rcon_port}/tcp',
                    ],
                    'volumes': [
                        f'{real_server_path}:/home/pok/arkserver',
                        f'{saved_path}:/home/pok/arkserver/ShooterGame/Saved',
                    ],
                    'working_dir': '/home/pok/arkserver',
                    'environment': [
                        f'INSTANCE_NAME={server.id}',
                        f'MAP_NAME={config.get("MAP_NAME", "TheIsland")}',
                        f'PORT={port}',
                        f'QUERY_PORT={query_port}',
                        f'RCON_PORT={rcon_port}',
                        f'SESSION_NAME={config.get("SESSION_NAME", server.name)}',
                        f'MAX_PLAYERS={server.max_players or 70}',
                        f'RCON_ENABLED={"True" if config.get("RCON_ENABLED", True) else "False"}',
                        f'BATTLEEYE={"True" if config.get("BATTLEEYE", False) else "False"}',
                        f'API={"True" if config.get("API", False) else "False"}',
                    ],
                }
            }
        }
        
        # Server Admin Password
        if config.get("ServerAdminPassword"):
            compose_data['services'][f'asa_{server.id}']['environment'].append(
                f'SERVER_ADMIN_PASSWORD={config.get("ServerAdminPassword")}'
            )
        
        # Server Password
        if config.get("ServerPassword"):
            compose_data['services'][f'asa_{server.id}']['environment'].append(
                f'SERVER_PASSWORD={config.get("ServerPassword")}'
            )
        
        # Mods
        if server.active_mods:
            mods_str = ",".join(str(mod_id) for mod_id in server.active_mods)
            compose_data['services'][f'asa_{server.id}']['environment'].append(
                f'ACTIVE_MODS={mods_str}'
            )
        
        # Custom Server Args
        if config.get("CUSTOM_SERVER_ARGS"):
            compose_data['services'][f'asa_{server.id}']['environment'].append(
                f'CUSTOM_SERVER_ARGS={config.get("CUSTOM_SERVER_ARGS")}'
            )
        
        # YAML fájl írása
        with open(compose_file, 'w') as f:
            yaml.dump(compose_data, f, default_flow_style=False, sort_keys=False)
        
        logger.info(f"Docker Compose fájl létrehozva: {compose_file}")
        return True
        
    except Exception as e:
        logger.error(f"Hiba a Docker Compose fájl létrehozásakor: {e}")
        return False

def start_server(server: ServerInstance, db: Session) -> Dict[str, any]:
    """
    Szerver indítása Docker-rel
    
    Args:
        server: ServerInstance objektum
        db: Database session
    
    Returns:
        Dict az eredménnyel
    """
    try:
        # Ellenőrizzük, hogy Docker elérhető-e
        if not check_docker_available():
            return {
                "success": False,
                "message": "Docker nem elérhető. Telepítsd a Docker-t vagy használd a közvetlen indítási módot."
            }
        
        docker_compose_cmd = get_docker_compose_cmd()
        if not docker_compose_cmd:
            return {
                "success": False,
                "message": "Docker Compose nem elérhető. Telepítsd a Docker Compose-t."
            }
        
        # Ellenőrizzük, hogy már fut-e
        container_name = f"asa_{server.id}"
        try:
            result = subprocess.run(
                ["docker", "ps", "-q", "-f", f"name=^{container_name}$"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                return {
                    "success": False,
                    "message": "A szerver már fut"
                }
        except Exception as e:
            logger.warning(f"Docker ps hiba: {e}")
        
        # Szerver útvonal lekérése (új struktúra: Servers/server_{server_id}/)
        if server.server_path:
            # Ha server_path van az adatbázisban, ellenőrizzük, hogy az új struktúrában van-e
            server_path = Path(server.server_path)
            # Ha a régi struktúrában van (user_X/server_Y), akkor az új struktúrára konvertáljuk
            if "user_" in str(server_path) or not server_path.exists():
                from app.services.symlink_service import get_servers_base_path
                servers_base = get_servers_base_path()
                server_path = servers_base / f"server_{server.id}"
        else:
            from app.services.symlink_service import get_servers_base_path
            servers_base = get_servers_base_path()
            server_path = servers_base / f"server_{server.id}"
        
        if not server_path or not server_path.exists():
            return {
                "success": False,
                "message": f"Szerver útvonal nem található: {server_path}"
            }
        
        # ServerFiles symlink útvonala (új struktúra: Servers/server_{server_id}/ServerFiles)
        serverfiles_link = server_path / "ServerFiles"
        if not serverfiles_link.exists() or not serverfiles_link.is_symlink():
            return {
                "success": False,
                "message": f"ServerFiles symlink nem található: {serverfiles_link}"
            }
        
        # Saved mappa útvonala (új struktúra: Servers/server_{server_id}/Saved/)
        saved_path = server_path / "Saved"
        if not saved_path or not saved_path.exists():
            return {
                "success": False,
                "message": f"Saved mappa nem található: {saved_path}"
            }
        
        # Docker Compose fájl létrehozása/frissítése
        compose_file = get_docker_compose_file(server)
        if not compose_file.exists():
            if not create_docker_compose_file(server, serverfiles_link, saved_path):
                return {
                    "success": False,
                    "message": "Docker Compose fájl létrehozása sikertelen"
                }
        else:
            # Ha létezik, frissítjük
            create_docker_compose_file(server, serverfiles_link, saved_path)
        
        # Docker Compose indítás
        compose_cmd = docker_compose_cmd.split() + ["-f", str(compose_file), "up", "-d"]
        
        result = subprocess.run(
            compose_cmd,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode != 0:
            logger.error(f"Docker Compose indítás hiba: {result.stderr}")
            return {
                "success": False,
                "message": f"Docker Compose indítás sikertelen: {result.stderr}"
            }
        
        # Státusz frissítése
        server.status = ServerStatus.RUNNING
        from datetime import datetime
        server.started_at = datetime.now()
        db.commit()
        
        logger.info(f"Szerver {server.id} indítva Docker-rel")
        
        return {
            "success": True,
            "message": "Szerver sikeresen elindítva Docker-rel"
        }
        
    except Exception as e:
        logger.error(f"Hiba a szerver indításakor: {e}")
        return {
            "success": False,
            "message": f"Hiba a szerver indításakor: {str(e)}"
        }

def stop_server(server: ServerInstance, db: Session) -> Dict[str, any]:
    """
    Szerver leállítása Docker-rel
    
    Args:
        server: ServerInstance objektum
        db: Database session
    
    Returns:
        Dict az eredménnyel
    """
    try:
        docker_compose_cmd = get_docker_compose_cmd()
        if not docker_compose_cmd:
            return {
                "success": False,
                "message": "Docker Compose nem elérhető"
            }
        
        compose_file = get_docker_compose_file(server)
        if not compose_file.exists():
            # Ha nincs compose fájl, akkor nincs mit leállítani
            server.status = ServerStatus.STOPPED
            server.started_at = None
            db.commit()
            return {
                "success": True,
                "message": "A szerver nem futott"
            }
        
        # Docker Compose leállítás
        compose_cmd = docker_compose_cmd.split() + ["-f", str(compose_file), "down"]
        
        result = subprocess.run(
            compose_cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        # Státusz frissítése
        server.status = ServerStatus.STOPPED
        server.started_at = None
        db.commit()
        
        logger.info(f"Szerver {server.id} leállítva Docker-rel")
        
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
    Szerver újraindítása Docker-rel
    
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
        docker_compose_cmd = get_docker_compose_cmd()
        if not docker_compose_cmd:
            return None
        
        compose_file = get_docker_compose_file(server)
        if not compose_file.exists():
            return None
        
        # Docker Compose parancs
        cmd = f"{docker_compose_cmd} -f {compose_file} up -d"
        return cmd
    except Exception as e:
        logger.error(f"Hiba a parancs generálásakor: {e}")
        return None

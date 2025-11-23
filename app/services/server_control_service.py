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
    Instance mappa útvonala (ahol a docker-compose fájl van)
    
    Args:
        server: ServerInstance objektum
    
    Returns:
        Path objektum az instance mappához
    """
    # A POK Manager script szerint: Instance_{instance_name}
    # Mi a szerver ID-t használjuk instance name-ként
    # A BASE_DIR a ServerFiles mappa szülő mappája
    # Példa: ark_serverfiles_base = /home/ai_developer/ZedinSteamManager/Server/ArkAscended/ServerFiles
    # BASE_DIR = /home/ai_developer/ZedinSteamManager/Server/ArkAscended
    base_dir = Path(settings.ark_serverfiles_base).parent if hasattr(settings, 'ark_serverfiles_base') else Path("/home/ai_developer/ZedinSteamManager/Server/ArkAscended")
    instance_dir = base_dir / f"Instance_{server.id}"
    return instance_dir

def get_docker_compose_file(server: ServerInstance) -> Path:
    """
    Docker Compose fájl útvonala
    
    Args:
        server: ServerInstance objektum
    
    Returns:
        Path objektum a docker-compose fájlhoz
    """
    instance_dir = get_instance_dir(server)
    return instance_dir / f"docker-compose-{server.id}.yaml"

def create_docker_compose_file(server: ServerInstance, server_path: Path, saved_path: Path) -> bool:
    """
    Docker Compose fájl létrehozása
    
    Args:
        server: ServerInstance objektum
        server_path: Szerver útvonal (symlink vagy valós mappa)
        saved_path: Dedikált Saved mappa útvonala
    
    Returns:
        True ha sikeres, False egyébként
    """
    try:
        instance_dir = get_instance_dir(server)
        instance_dir.mkdir(parents=True, exist_ok=True)
        
        # A POK Manager script szerint az Instance_{server_id}/Saved mappa NEM kell,
        # mert a Saved mappa a dedikált Saved mappában van (user_{user_id}/server_{server_id}_saved)
        # A Docker Compose fájlban a saved_path-et közvetlenül használjuk
        # DE: a POK Manager script létrehozza az Instance_{server_id}/Saved mappát, szóval mi is
        # (bár valójában nem használjuk, de kompatibilitás miatt létrehozzuk)
        saved_dir = instance_dir / "Saved"
        if not saved_dir.exists():
            saved_dir.mkdir(parents=True, exist_ok=True)
        
        # Ha a saved_path egy symlink, követjük
        if saved_path.is_symlink():
            try:
                saved_path = saved_path.resolve()
            except Exception as e:
                logger.warning(f"Symlink követése sikertelen: {e}")
        
        # Ha a server_path egy symlink, követjük
        real_server_path = server_path
        if server_path.is_symlink():
            try:
                real_server_path = server_path.resolve()
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
        
        # Saved mappa útvonala
        # A get_server_dedicated_saved_path egy server_path-et vár, nem server_id-t
        # Szóval először meg kell találnunk a server_path-et
        saved_path = get_server_dedicated_saved_path(server_path)
        if not saved_path or not saved_path.exists():
            return {
                "success": False,
                "message": "Saved mappa nem található"
            }
        
        # Docker Compose fájl létrehozása/frissítése
        compose_file = get_docker_compose_file(server)
        if not compose_file.exists():
            if not create_docker_compose_file(server, server_path, saved_path):
                return {
                    "success": False,
                    "message": "Docker Compose fájl létrehozása sikertelen"
                }
        else:
            # Ha létezik, frissítjük
            create_docker_compose_file(server, server_path, saved_path)
        
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

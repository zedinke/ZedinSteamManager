"""
Szerver indítási/leállítási/restart szolgáltatás - Docker támogatással
"""

import subprocess
import os
import signal
import psutil
import shutil
import time
import socket
import struct
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict
from sqlalchemy.orm import Session
from app.database import ServerInstance, ServerStatus, Cluster
from app.services.symlink_service import get_server_path, get_server_dedicated_saved_path
from app.config import settings
import json
import logging
import yaml

logger = logging.getLogger(__name__)

def send_rcon_command(host: str, port: int, password: str, command: str, timeout: int = 5) -> Optional[str]:
    """
    RCON parancs küldése ARK szervernek (Source RCON protokoll)
    
    Args:
        host: Szerver host (általában localhost)
        port: RCON port
        password: RCON jelszó
        command: Parancs (pl. "saveworld")
        timeout: Timeout másodpercben
    
    Returns:
        Válasz a szervertől vagy None hiba esetén
    """
    try:
        # Socket létrehozása
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        
        # Kapcsolódás
        sock.connect((host, port))
        
        # RCON autentikáció
        # SERVERDATA_AUTH packet
        auth_packet = struct.pack('<III', 0, 3, len(password)) + password.encode('utf-8') + b'\x00\x00'
        auth_packet = struct.pack('<I', len(auth_packet)) + auth_packet
        sock.send(auth_packet)
        
        # Válasz olvasása (2 packet: SERVERDATA_AUTH_RESPONSE és SERVERDATA_RESPONSE_VALUE)
        try:
            response = sock.recv(4096)
            if len(response) < 4:
                logger.warning("RCON autentikáció válasz túl rövid")
                sock.close()
                return None
            
            # Ellenőrizzük, hogy az autentikáció sikeres volt-e
            # Ha a válasz ID -1, akkor sikertelen volt
            response_id = struct.unpack('<I', response[4:8])[0]
            if response_id == 0xFFFFFFFF:
                logger.warning("RCON autentikáció sikertelen")
                sock.close()
                return None
        except socket.timeout:
            logger.warning("RCON autentikáció timeout")
            sock.close()
            return None
        
        # Parancs küldése
        # SERVERDATA_EXECCOMMAND packet
        command_packet = struct.pack('<III', 0, 2, len(command)) + command.encode('utf-8') + b'\x00\x00'
        command_packet = struct.pack('<I', len(command_packet)) + command_packet
        sock.send(command_packet)
        
        # Válasz olvasása
        try:
            response = sock.recv(4096)
            if len(response) >= 4:
                response_length = struct.unpack('<I', response[0:4])[0]
                if len(response) >= response_length + 4:
                    response_body = response[12:12+response_length-10].decode('utf-8', errors='ignore')
                    sock.close()
                    return response_body
        except socket.timeout:
            logger.warning("RCON parancs válasz timeout")
        
        sock.close()
        return None
        
    except Exception as e:
        logger.error(f"RCON parancs hiba: {e}")
        return None

def test_rcon_connection(host: str, port: int, password: str, timeout: int = 3) -> bool:
    """
    RCON kapcsolat tesztelése
    
    Args:
        host: Szerver host (általában localhost)
        port: RCON port
        password: RCON jelszó
        timeout: Timeout másodpercben
    
    Returns:
        True ha az RCON kapcsolat működik, False egyébként
    """
    if not password or not password.strip():
        return False
    
    try:
        # Próbálunk egy egyszerű parancsot küldeni (pl. "listplayers" vagy csak egy üres parancs)
        result = send_rcon_command(host, port, password, "listplayers", timeout=timeout)
        # Ha van válasz (akár üres is), akkor működik
        return result is not None
    except Exception as e:
        logger.debug(f"RCON kapcsolat teszt hiba: {e}")
        return False

def check_process_running_in_container(container_name: str, process_pattern: str = "ArkAscendedServer.exe") -> bool:
    """
    Ellenőrzi, hogy egy folyamat fut-e a Docker konténerben
    
    Args:
        container_name: Docker konténer neve
        process_pattern: Folyamat keresési minta (pl. "ArkAscendedServer.exe")
    
    Returns:
        True ha a folyamat fut, False egyébként
    """
    try:
        result = subprocess.run(
            ["docker", "exec", container_name, "pgrep", "-f", process_pattern],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0 and result.stdout.strip() != ""
    except Exception as e:
        logger.warning(f"Folyamat ellenőrzés hiba a konténerben: {e}")
        return False

def wait_for_process_shutdown(container_name: str, process_pattern: str = "ArkAscendedServer.exe", max_wait_seconds: int = 180) -> bool:
    """
    Várja, hogy a folyamat leálljon a Docker konténerben
    
    Args:
        container_name: Docker konténer neve
        process_pattern: Folyamat keresési minta (pl. "ArkAscendedServer.exe")
        max_wait_seconds: Maximum várakozási idő másodpercben (alapértelmezett: 180 = 3 perc)
    
    Returns:
        True ha a folyamat leállt, False ha timeout
    """
    check_interval = 5  # 5 másodpercenként ellenőrzünk
    elapsed = 0
    
    logger.info(f"Várakozás, hogy a folyamat leálljon a konténerben (max {max_wait_seconds} másodperc)...")
    
    while elapsed < max_wait_seconds:
        # Ellenőrizzük, hogy a konténer még fut-e
        try:
            result = subprocess.run(
                ["docker", "ps", "-q", "-f", f"name=^{container_name}$"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if not result.stdout.strip():
                logger.info("Konténer már leállt")
                return True
        except Exception as e:
            logger.warning(f"Konténer ellenőrzés hiba: {e}")
            return True  # Ha nem tudjuk ellenőrizni, feltételezzük, hogy leállt
        
        # Ellenőrizzük, hogy a folyamat még fut-e
        if not check_process_running_in_container(container_name, process_pattern):
            logger.info("Folyamat leállt")
            return True
        
        time.sleep(check_interval)
        elapsed += check_interval
        if elapsed % 30 == 0:  # Minden 30 másodpercben logolunk
            logger.info(f"Várakozás... ({elapsed}/{max_wait_seconds} másodperc)")
    
    logger.warning(f"Timeout: a folyamat nem állt le {max_wait_seconds} másodperc alatt")
    return False

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

def create_docker_compose_file(server: ServerInstance, serverfiles_link: Path, saved_path: Path, db: Optional[Session] = None) -> bool:
    """
    Docker Compose fájl létrehozása (új struktúra: Servers/server_{server_id}/docker-compose.yaml)
    A konfigurációkat a Saved/Config/WindowsServer mappából olvassa be
    
    Args:
        server: ServerInstance objektum
        serverfiles_link: ServerFiles symlink útvonala (Servers/server_{server_id}/ServerFiles)
        saved_path: Dedikált Saved mappa útvonala (Servers/server_{server_id}/Saved/)
        db: Database session (opcionális, csak cluster_id lekéréséhez szükséges)
    
    Returns:
        True ha sikeres, False egyébként
    """
    try:
        instance_dir = get_instance_dir(server)  # Servers/server_{server_id}/
        instance_dir.mkdir(parents=True, exist_ok=True)
        # AZONNAL beállítjuk a jogosultságokat (ne root jogosultságokkal jöjjön létre!)
        from app.services.symlink_service import ensure_permissions
        ensure_permissions(instance_dir)
        
        # FONTOS: Ellenőrizzük és javítjuk a volume mount útvonalak szülő mappáit is!
        # Mert ha a Docker volume mount-nál a mappa nem létezik, root jogosultságokkal hozhatja létre
        import os
        import stat
        from app.config import settings
        current_uid = os.getuid()
        current_gid = os.getgid()
        
        # FONTOS: Először ellenőrizzük és javítjuk a base mappát (ServerFiles)!
        # Mert ha az root jogosultságokkal létezik, akkor az új mappák is root jogosultságokkal jönnek létre
        base_path = Path(settings.ark_serverfiles_base)
        
        # Real server path meghatározása (symlink célja)
        real_server_path = serverfiles_link.resolve() if serverfiles_link.is_symlink() else serverfiles_link
        
        if base_path.exists():
            try:
                stat_info = base_path.stat()
                if stat_info.st_uid == 0 and current_uid != 0:
                    logger.warning(f"Root jogosultságokkal létező base mappa észlelve: {base_path}")
                    try:
                        os.chmod(base_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
                        os.chown(base_path, current_uid, current_gid)
                        logger.info(f"✓ Base mappa jogosultságok javítva: {base_path}")
                    except (PermissionError, OSError) as e:
                        logger.error(f"⚠️ Nem sikerült javítani a base mappa jogosultságait {base_path}: {e}")
            except (PermissionError, OSError):
                pass
        
        # Ellenőrizzük a real_server_path szülő mappáit (user_* mappa)
        # FONTOS: Lépésenként hozzuk létre, hogy minden lépés után beállíthassuk a jogosultságokat!
        if not real_server_path.exists():
            # FONTOS: Először ellenőrizzük és javítjuk a base mappát (ServerFiles)!
            # Mert ha az root jogosultságokkal létezik, akkor az új mappák is root jogosultságokkal jönnek létre
            if base_path.exists():
                try:
                    stat_info = base_path.stat()
                    if stat_info.st_uid == 0 and current_uid != 0:
                        logger.warning(f"Root jogosultságokkal létező base mappa észlelve: {base_path}")
                        try:
                            os.chmod(base_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
                            os.chown(base_path, current_uid, current_gid)
                            logger.info(f"✓ Base mappa jogosultságok javítva: {base_path}")
                        except (PermissionError, OSError) as e:
                            logger.error(f"⚠️ Nem sikerült javítani a base mappa jogosultságait {base_path}: {e}")
                except (PermissionError, OSError):
                    pass
            
            # Először a user_* mappát (parent)
            if not real_server_path.parent.exists():
                # FONTOS: Mielőtt létrehoznánk, biztosítjuk, hogy a base mappa megfelelő jogosultságokkal létezik!
                if base_path.exists():
                    ensure_permissions(base_path)
                real_server_path.parent.mkdir(parents=True, exist_ok=True)
                # AZONNAL beállítjuk a jogosultságokat!
                ensure_permissions(real_server_path.parent)
            else:
                # Ha létezik, ellenőrizzük a jogosultságokat
                ensure_permissions(real_server_path.parent)
            
            # Most a tényleges mappát (latest vagy verzió)
            # FONTOS: Mielőtt létrehoznánk, biztosítjuk, hogy a user_* mappa megfelelő jogosultságokkal létezik!
            if real_server_path.parent.exists():
                ensure_permissions(real_server_path.parent)
            real_server_path.mkdir(parents=True, exist_ok=True)
            # AZONNAL beállítjuk a jogosultságokat!
            ensure_permissions(real_server_path)
        else:
            # Ha létezik, ellenőrizzük a jogosultságokat
            ensure_permissions(real_server_path)
            # Ellenőrizzük a szülő mappát is
            if real_server_path.parent.exists():
                ensure_permissions(real_server_path.parent)
            # Ellenőrizzük a base mappát is
            if base_path.exists():
                ensure_permissions(base_path)
        
        # Ellenőrizzük a saved_path szülő mappáit is
        # FONTOS: A Saved mappa Docker volume mount, ezért a Docker konténer UID/GID-jét (1000:1000) kell használni!
        from app.services.symlink_service import ensure_docker_container_permissions
        if saved_path.exists() or not saved_path.exists():
            if not saved_path.exists():
                saved_path.mkdir(parents=True, exist_ok=True)
                # Docker konténer jogosultságok beállítása (1000:1000)
                ensure_docker_container_permissions(saved_path, recursive=True)
            else:
                # Docker konténer jogosultságok beállítása (1000:1000)
                ensure_docker_container_permissions(saved_path, recursive=True)
                # Ellenőrizzük a szülő mappákat is
                for parent in [saved_path.parent, saved_path.parent.parent]:
                    if parent.exists():
                        ensure_docker_container_permissions(parent)
        
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
        
        # Konfiguráció beolvasása a Saved/Config/WindowsServer mappából
        config_path = saved_path / "Config" / "WindowsServer"
        game_user_settings_path = config_path / "GameUserSettings.ini"
        
        # Konfiguráció beolvasása INI fájlból
        config_values = {}
        if game_user_settings_path.exists():
            try:
                from app.services.ark_config_service import parse_ini_file
                ini_data = parse_ini_file(game_user_settings_path)
                server_settings = ini_data.get("ServerSettings", {})
                session_settings = ini_data.get("SessionSettings", {})
                
                # Beállítások kiolvasása (a kulcsok lehetnek különböző formátumokban)
                # MAP_NAME a config-ból vagy alapértelmezett
                config_values["MAP_NAME"] = server.config.get("MAP_NAME", "TheIsland") if server.config else "TheIsland"
                session_name_from_config = session_settings.get("SessionName") or server_settings.get("SessionName") or server.name
                # Ha "Server_name" van beállítva (placeholder), akkor használjuk a server.name-t
                if session_name_from_config == "Server_name" or session_name_from_config == "server_name":
                    config_values["SESSION_NAME"] = server.name
                else:
                    config_values["SESSION_NAME"] = session_name_from_config
                config_values["ServerAdminPassword"] = server_settings.get("ServerAdminPassword") or server.config.get("ServerAdminPassword", "") if server.config else ""
                config_values["ServerPassword"] = server_settings.get("ServerPassword") or server.config.get("ServerPassword", "") if server.config else ""
                
                # Boolean értékek kezelése
                rcon_enabled = server_settings.get("RCONEnabled")
                if rcon_enabled is None:
                    rcon_enabled = server.config.get("RCON_ENABLED", True) if server.config else True
                config_values["RCON_ENABLED"] = str(rcon_enabled).lower() in ("true", "1", "yes", "on")
                
                battleeye = server_settings.get("BATTLEEYE")
                if battleeye is None:
                    battleeye = server.config.get("BATTLEEYE", False) if server.config else False
                config_values["BATTLEEYE"] = str(battleeye).lower() in ("true", "1", "yes", "on")
                
                api = server_settings.get("API")
                if api is None:
                    api = server.config.get("API", False) if server.config else False
                config_values["API"] = str(api).lower() in ("true", "1", "yes", "on")
                
                config_values["MAX_PLAYERS"] = server_settings.get("MaxPlayers") or server.max_players or 70
            except Exception as e:
                logger.warning(f"Konfiguráció beolvasása sikertelen, alapértelmezett értékeket használunk: {e}")
        
        # Ha nincs konfiguráció, akkor az adatbázisból vagy alapértelmezett értékeket használunk
        if not config_values:
            config = server.config or {}
            config_values = {
                "MAP_NAME": config.get("MAP_NAME", "TheIsland"),
                "SESSION_NAME": config.get("SESSION_NAME", server.name),
                "ServerAdminPassword": config.get("ServerAdminPassword", ""),
                "ServerPassword": config.get("ServerPassword", ""),
                "RCON_ENABLED": config.get("RCON_ENABLED", True),
                "BATTLEEYE": config.get("BATTLEEYE", False),
                "API": config.get("API", False),
                "MAX_PLAYERS": server.max_players or 70,
            }
        
        # FONTOS: Ha a config_values-ban nincs ServerAdminPassword, de a server.config-ban van, akkor használjuk azt
        # Ez biztosítja, hogy mindig legyen érték, ha a szerver config-ban van
        if not config_values.get("ServerAdminPassword") and server.config:
            server_admin_from_config = server.config.get("ServerAdminPassword", "")
            if server_admin_from_config:
                config_values["ServerAdminPassword"] = server_admin_from_config
                logger.info(f"DEBUG: ServerAdminPassword beállítva server.config-ból: {server_admin_from_config[:3]}...")
        
        # Ha még mindig nincs érték, akkor próbáljuk meg közvetlenül a server.config-ból
        if not config_values.get("ServerAdminPassword") and server.config:
            direct_admin_password = server.config.get("ServerAdminPassword")
            if direct_admin_password:
                config_values["ServerAdminPassword"] = direct_admin_password
                logger.info(f"DEBUG: ServerAdminPassword beállítva közvetlenül server.config-ból: {direct_admin_password[:3]}...")
        
        # Portok
        port = server.port or settings.ark_default_port
        query_port = server.query_port or (port + 2)
        rcon_port = server.rcon_port or settings.ark_default_rcon_port
        
        # Docker image és útvonalak meghatározása
        # Csak saját Docker image-t használunk: zedinarkmanager/ark-server:latest
        docker_image = getattr(settings, 'ark_docker_image', 'zedinarkmanager/ark-server:latest')
        
        # Saját Docker image: /home/ai_developer/arkserver struktúra
        container_work_dir = '/home/ai_developer/arkserver'
        container_saved_path = '/home/ai_developer/arkserver/ShooterGame/Saved'
        
        # Docker Compose YAML összeállítása
        compose_data = {
            'version': '2.4',
            'services': {
                'asaserver': {
                    'image': docker_image,
                    # Container név: egyedi kell legyen, szerver ID alapján
                    # Prefix: 'zedin_asa_' hogy ne ütközzön más rendszerekkel
                    'container_name': f'zedin_asa_{server.id}',
                    'restart': 'unless-stopped',
                    'ports': [
                        f'{port}:{port}/tcp',
                        f'{port}:{port}/udp',
                        f'{rcon_port}:{rcon_port}/tcp',
                    ],
                    'volumes': [
                        f'{real_server_path}:{container_work_dir}',
                        f'{saved_path}:{container_saved_path}',
                    ],
                    'working_dir': container_work_dir,
                    'environment': [
                        f'INSTANCE_NAME={server.id}',
                        f'MAP_NAME={config_values.get("MAP_NAME", "TheIsland")}',
                        f'ASA_PORT={port}',
                        f'QUERY_PORT={query_port}',
                        f'RCON_PORT={rcon_port}',
                        f'SESSION_NAME={config_values.get("SESSION_NAME", server.name)}',
                        f'MAX_PLAYERS={config_values.get("MAX_PLAYERS", server.max_players or 70)}',
                        f'RCON_ENABLED={"True" if config_values.get("RCON_ENABLED", True) else "False"}',
                        f'BATTLEEYE={"True" if config_values.get("BATTLEEYE", False) else "False"}',
                        f'API={"True" if config_values.get("API", False) else "False"}',
                        f'ARK_SERVER_DIR={container_work_dir}',  # A mountolt mappa, ahol a ServerFiles található
                        f'UPDATE_SERVER=False',  # Ne telepítsen újra, ha a fájlok már a hoston vannak
                    ],
                }
            }
        }
        
        # Server Admin Password - mindig bekerül, ha van értéke
        server_admin_password_value = config_values.get("ServerAdminPassword", "")
        if server_admin_password_value:
            compose_data['services']['asaserver']['environment'].append(
                f'SERVER_ADMIN_PASSWORD={server_admin_password_value}'
            )
            logger.info(f"DEBUG: SERVER_ADMIN_PASSWORD hozzáadva a Docker Compose-hoz: {server_admin_password_value[:3]}... (hossz: {len(server_admin_password_value)})")
        else:
            logger.warning(f"DEBUG: SERVER_ADMIN_PASSWORD NEM került hozzáadásra! config_values.get('ServerAdminPassword'): '{server_admin_password_value}'")
            logger.warning(f"DEBUG: config_values keys: {list(config_values.keys())}")
            logger.warning(f"DEBUG: server.config: {server.config}")
        
        # Server Password
        if config_values.get("ServerPassword"):
            compose_data['services']['asaserver']['environment'].append(
                f'SERVER_PASSWORD={config_values.get("ServerPassword")}'
            )
        
        # Mods
        if server.active_mods:
            mods_str = ",".join(str(mod_id) for mod_id in server.active_mods)
            compose_data['services']['asaserver']['environment'].append(
                f'MOD_IDS={mods_str}'
            )
        
        # Passive Mods
        config = server.config or {}
        if config.get("PASSIVE_MODS"):
            passive_mods_str = config.get("PASSIVE_MODS")
            compose_data['services']['asaserver']['environment'].append(
                f'PASSIVE_MODS={passive_mods_str}'
            )
        
        # Cluster ID
        if server.cluster_id and db:
            cluster = db.query(Cluster).filter(Cluster.id == server.cluster_id).first()
            if cluster and cluster.cluster_id:
                compose_data['services']['asaserver']['environment'].append(
                    f'CLUSTER_ID={cluster.cluster_id}'
                )
        
        # Custom Server Args
        if config.get("CUSTOM_SERVER_ARGS"):
            compose_data['services']['asaserver']['environment'].append(
                f'CUSTOM_SERVER_ARGS={config.get("CUSTOM_SERVER_ARGS")}'
            )
        
        # RAM limit beállítása (ha van beállítva)
        # Total RAM = ram_limit_gb (alapértelmezett) + purchased_ram_gb (vásárolt)
        total_ram_gb = (server.ram_limit_gb or 0) + (server.purchased_ram_gb or 0)
        if total_ram_gb > 0:
            # Docker memória limit: GB -> MB konverzió
            memory_limit_mb = total_ram_gb * 1024
            compose_data['services']['asaserver']['mem_limit'] = f'{memory_limit_mb}M'
        
        # Debug információk
        logger.info(f"Docker Compose fájl generálása:")
        logger.info(f"  - ServerFiles path: {real_server_path} (exists: {real_server_path.exists()})")
        logger.info(f"  - Saved path: {saved_path} (exists: {saved_path.exists()})")
        logger.info(f"  - Container work dir: {container_work_dir}")
        logger.info(f"  - Container saved path: {container_saved_path}")
        logger.info(f"  - Docker image: {docker_image}")
        
        # Ellenőrizzük, hogy a szerverfájlok léteznek-e
        if not real_server_path.exists():
            logger.warning(f"ServerFiles útvonal nem létezik: {real_server_path}")
        else:
            # Ellenőrizzük, hogy van-e ShooterGame mappa
            shooter_game_path = real_server_path / "ShooterGame"
            if not shooter_game_path.exists():
                logger.warning(f"ShooterGame mappa nem létezik: {shooter_game_path}")
            else:
                # Ellenőrizzük a Binaries mappát
                binaries_path = shooter_game_path / "Binaries"
                if not binaries_path.exists():
                    logger.warning(f"Binaries mappa nem létezik: {binaries_path}")
                    logger.warning(f"  - ShooterGame tartalma: {[item.name for item in shooter_game_path.iterdir()] if shooter_game_path.exists() else 'N/A'}")
                else:
                    # Ellenőrizzük a Linux binárist (csak linux64/ mappa létezik, ShooterGame/Binaries/Linux nem)
                    linux_binary_linux64 = real_server_path / "linux64" / "ShooterGameServer"
                    # Ellenőrizzük a Windows binárist is (ArkAscendedServer.exe, nem ShooterGameServer.exe)
                    win64_binary = binaries_path / "Win64" / "ArkAscendedServer.exe"
                    
                    # Csak a linux64/ mappát ellenőrizzük
                    linux_binary = linux_binary_linux64 if linux_binary_linux64.exists() else None
                    
                    # Nézzük meg, mi van a Binaries mappában
                    binaries_contents = [item.name for item in binaries_path.iterdir()] if binaries_path.exists() else []
                    logger.info(f"Binaries mappa tartalma: {binaries_contents}")
                    
                    if linux_binary:
                        logger.info(f"Linux ShooterGameServer bináris megtalálva: {linux_binary}")
                    elif win64_binary.exists():
                        logger.info(f"Windows ArkAscendedServer.exe bináris megtalálva: {win64_binary} (Wine-nal fog futni)")
                    else:
                        logger.warning(f"Bináris nem található:")
                        logger.warning(f"  - Linux (linux64/ShooterGameServer): {linux_binary_linux64}")
                        logger.warning(f"  - Windows (ShooterGame/Binaries/Win64/ArkAscendedServer.exe): {win64_binary}")
                        logger.warning(f"  - Windows: {win64_binary}")
                        logger.warning(f"  - Binaries mappa tartalma: {binaries_contents}")
                        if binaries_path.exists():
                            # Nézzük meg részletesebben, mi van a Binaries mappában
                            for item in binaries_path.iterdir():
                                if item.is_dir():
                                    sub_contents = [subitem.name for subitem in item.iterdir()] if item.exists() else []
                                    logger.warning(f"  - {item.name}/ tartalma: {sub_contents[:10]}")
                        # Ellenőrizzük a linux64/ mappát is
                        if (real_server_path / "linux64").exists():
                            linux64_contents = [item.name for item in (real_server_path / "linux64").iterdir()] if (real_server_path / "linux64").exists() else []
                            logger.warning(f"  - linux64/ mappa tartalma: {linux64_contents[:10]}")
        
        # YAML fájl írása
        with open(compose_file, 'w') as f:
            yaml.dump(compose_data, f, default_flow_style=False, sort_keys=False)
        
        logger.info(f"Docker Compose fájl létrehozva: {compose_file}")
        
        # Indítási parancs fájl létrehozása/frissítése
        update_start_command_file(server, compose_file, compose_data)
        
        return True
        
    except Exception as e:
        logger.error(f"Hiba a Docker Compose fájl létrehozásakor: {e}")
        import traceback
        traceback.print_exc()
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
        container_name = f"zedin_asa_{server.id}"
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
        # Mindig a helyes útvonalat használjuk, ne a server.server_path-et közvetlenül
        from app.services.symlink_service import get_servers_base_path
        servers_base = get_servers_base_path()
        server_path = servers_base / f"server_{server.id}"
        
        # Ha a server.server_path tartalmazza a ServerFiles-t, akkor eltávolítjuk
        # Ez biztosítja, hogy mindig a helyes útvonalat használjuk
        if server.server_path:
            server_path_str = str(server.server_path).replace("\\", "/")
            # Ha a path végén van ServerFiles, akkor eltávolítjuk
            if server_path_str.endswith("/ServerFiles"):
                server_path = Path(server_path_str).parent
            # Ha a path-ben van ServerFiles, de nem a helyes struktúrában, akkor újraépítjük
            elif "/ServerFiles/" in server_path_str or server_path_str.count("/ServerFiles") > 1:
                # Duplikált ServerFiles esetén újraépítjük
                server_path = servers_base / f"server_{server.id}"
        
        if not server_path or not server_path.exists():
            return {
                "success": False,
                "message": f"Szerver útvonal nem található: {server_path}"
            }
        
        # ServerFiles symlink útvonala (új struktúra: Servers/server_{server_id}/ServerFiles)
        serverfiles_link = server_path / "ServerFiles"
        
        # Debug logging
        logger.info(f"Server path: {server_path}")
        logger.info(f"ServerFiles link path: {serverfiles_link}")
        logger.info(f"ServerFiles link exists: {serverfiles_link.exists()}")
        if serverfiles_link.exists():
            logger.info(f"ServerFiles link is symlink: {serverfiles_link.is_symlink()}")
            if serverfiles_link.is_symlink():
                try:
                    logger.info(f"ServerFiles symlink target: {serverfiles_link.readlink()}")
                except Exception as e:
                    logger.warning(f"Symlink target olvasása sikertelen: {e}")
        
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
        
        # FONTOS: Docker indítás előtt biztosítjuk, hogy a volume mount útvonalak létezzenek megfelelő jogosultságokkal!
        # Mert ha a Docker volume mount-nál a mappa nem létezik, root jogosultságokkal hozhatja létre
        from app.services.symlink_service import ensure_permissions
        import os
        import stat
        from app.config import settings
        
        # Ellenőrizzük a real_server_path-et (ServerFiles symlink célja)
        real_server_path = serverfiles_link.resolve() if serverfiles_link.is_symlink() else serverfiles_link
        
        # FONTOS: Először ellenőrizzük és javítjuk a base mappát (ServerFiles)!
        base_path = Path(settings.ark_serverfiles_base)
        if base_path.exists():
            try:
                stat_info = base_path.stat()
                current_uid = os.getuid()
                if stat_info.st_uid == 0 and current_uid != 0:
                    logger.warning(f"Root jogosultságokkal létező base mappa észlelve: {base_path}")
                    try:
                        os.chmod(base_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
                        os.chown(base_path, current_uid, os.getgid())
                        logger.info(f"✓ Base mappa jogosultságok javítva: {base_path}")
                    except (PermissionError, OSError) as e:
                        logger.error(f"⚠️ Nem sikerült javítani a base mappa jogosultságait {base_path}: {e}")
            except (PermissionError, OSError):
                pass
        
        # FONTOS: Ellenőrizzük, hogy a real_server_path létezik-e és megfelelő jogosultságokkal
        # Mert ha nem létezik, a Docker volume mount root jogosultságokkal hozhatja létre!
        logger.info(f"Ellenőrzés: real_server_path = {real_server_path}")
        logger.info(f"real_server_path.exists() = {real_server_path.exists()}")
        
        if not real_server_path.exists():
            logger.warning(f"⚠️ real_server_path nem létezik, létrehozzuk: {real_server_path}")
            # Létrehozzuk lépésenként
            if not real_server_path.parent.exists():
                logger.info(f"Szülő mappa létrehozása: {real_server_path.parent}")
                real_server_path.parent.mkdir(parents=True, exist_ok=True)
                ensure_permissions(real_server_path.parent)
                logger.info(f"✓ Szülő mappa létrehozva és jogosultságok beállítva: {real_server_path.parent}")
            real_server_path.mkdir(parents=True, exist_ok=True)
            ensure_permissions(real_server_path)
            logger.info(f"✓ real_server_path létrehozva és jogosultságok beállítva: {real_server_path}")
            
            # Ellenőrizzük, hogy tényleg létrejött-e és megfelelő jogosultságokkal
            if real_server_path.exists():
                try:
                    stat_info = real_server_path.stat()
                    current_uid = os.getuid()
                    if stat_info.st_uid == 0 and current_uid != 0:
                        logger.error(f"❌ HIBA: real_server_path root jogosultságokkal jött létre: {real_server_path}")
                        logger.error(f"   Stat: uid={stat_info.st_uid}, gid={stat_info.st_gid}")
                    else:
                        logger.info(f"✓ real_server_path megfelelő jogosultságokkal létezik: uid={stat_info.st_uid}, gid={stat_info.st_gid}")
                except Exception as e:
                    logger.error(f"⚠️ Nem sikerült ellenőrizni a real_server_path jogosultságait: {e}")
        else:
            ensure_permissions(real_server_path)
            if real_server_path.parent.exists():
                ensure_permissions(real_server_path.parent)
            logger.info(f"✓ real_server_path már létezik, jogosultságok ellenőrizve: {real_server_path}")
        
        # Ellenőrizzük a saved_path-et is
        logger.info(f"Ellenőrzés: saved_path = {saved_path}")
        logger.info(f"saved_path.exists() = {saved_path.exists()}")
        
        if not saved_path.exists():
            logger.warning(f"⚠️ saved_path nem létezik, létrehozzuk: {saved_path}")
            saved_path.mkdir(parents=True, exist_ok=True)
            ensure_permissions(saved_path)
            logger.info(f"✓ saved_path létrehozva és jogosultságok beállítva: {saved_path}")
            
            # Ellenőrizzük, hogy tényleg létrejött-e és megfelelő jogosultságokkal
            if saved_path.exists():
                try:
                    stat_info = saved_path.stat()
                    current_uid = os.getuid()
                    if stat_info.st_uid == 0 and current_uid != 0:
                        logger.error(f"❌ HIBA: saved_path root jogosultságokkal jött létre: {saved_path}")
                        logger.error(f"   Stat: uid={stat_info.st_uid}, gid={stat_info.st_gid}")
                    else:
                        logger.info(f"✓ saved_path megfelelő jogosultságokkal létezik: uid={stat_info.st_uid}, gid={stat_info.st_gid}")
                except Exception as e:
                    logger.error(f"⚠️ Nem sikerült ellenőrizni a saved_path jogosultságait: {e}")
        else:
            ensure_permissions(saved_path)
            logger.info(f"✓ saved_path már létezik, jogosultságok ellenőrizve: {saved_path}")
        
        # Docker Compose fájl létrehozása/frissítése
        # Mindig frissítjük, hogy a konfigurációk szinkronban legyenek
        compose_file = get_docker_compose_file(server)
        try:
            if not create_docker_compose_file(server, serverfiles_link, saved_path, db):
                error_details = f"Docker Compose fájl létrehozása sikertelen. Ellenőrizd a logokat."
                logger.error(error_details)
                return {
                    "success": False,
                    "message": error_details
                }
        except Exception as e:
            error_details = f"Docker Compose fájl létrehozása hiba: {str(e)}"
            logger.error(error_details, exc_info=True)
            return {
                "success": False,
                "message": error_details
            }
        
        # Log fájl létrehozása a szerver indításához
        log_file = server_path / f"startup_log_{int(time.time())}.txt"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        # AZONNAL beállítjuk a jogosultságokat (ne root jogosultságokkal jöjjön létre!)
        from app.services.symlink_service import ensure_permissions
        ensure_permissions(log_file.parent)
        
        with open(log_file, 'w', encoding='utf-8') as log_f:
            log_f.write(f"=== Szerver indítás log - {datetime.now().isoformat()} ===\n")
            log_f.write(f"Szerver ID: {server.id}\n")
            log_f.write(f"Container name: zedin_asa_{server.id}\n")
            log_f.write(f"Compose file: {compose_file}\n")
            # Real server path (symlink célja)
            real_server_path = serverfiles_link.resolve() if serverfiles_link.is_symlink() else serverfiles_link
            log_f.write(f"ServerFiles (symlink): {serverfiles_link}\n")
            log_f.write(f"ServerFiles (tényleges): {real_server_path}\n")
            log_f.write(f"Saved path: {saved_path}\n")
            log_f.write("\n")
            
            # Docker Compose indítás részletes logolással
            compose_cmd = docker_compose_cmd.split() + ["-f", str(compose_file), "up", "-d"]
            log_f.write(f"Docker Compose parancs: {' '.join(compose_cmd)}\n")
            log_f.write("\n--- Docker Compose kimenet ---\n")
            log_f.flush()
            
            # Docker Compose futtatása és kimenet streamelése
            process = subprocess.Popen(
                compose_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Valós idejű log streamelés
            for line in process.stdout:
                log_f.write(line)
                log_f.flush()
                logger.info(f"[Docker] {line.strip()}")
            
            process.wait()
            return_code = process.returncode
            
            log_f.write(f"\n--- Docker Compose exit code: {return_code} ---\n")
            log_f.flush()
        
        if return_code != 0:
            # Olvassuk be a log fájl tartalmát
            with open(log_file, 'r', encoding='utf-8') as log_f:
                log_content = log_f.read()
            
            logger.error(f"Docker Compose indítás hiba (log: {log_file}):\n{log_content[-1000:]}")
            return {
                "success": False,
                "message": f"Docker Compose indítás sikertelen. Log fájl: {log_file}",
                "log_file": str(log_file)
            }
        
        # Várakozás, hogy a konténer elinduljon (2 másodperc)
        time.sleep(2)
        
        # Ellenőrizzük, hogy a konténer ténylegesen fut-e
        container_name = f"zedin_asa_{server.id}"
        check_result = subprocess.run(
            ["docker", "ps", "-q", "-f", f"name=^{container_name}$"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if check_result.returncode != 0 or not check_result.stdout.strip():
            # A konténer nem fut, nézzük meg a logokat
            logger.warning(f"Konténer {container_name} nem fut az indítás után")
            
            # Konténer státusz ellenőrzése (leállt konténer is lehet)
            inspect_result = subprocess.run(
                ["docker", "ps", "-a", "-q", "-f", f"name=^{container_name}$"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if inspect_result.stdout.strip():
                # A konténer létezik, de nem fut - nézzük meg a logokat
                log_result = subprocess.run(
                    ["docker", "logs", "--tail", "50", container_name],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                log_output = log_result.stdout or log_result.stderr or "Nincs log kimenet"
                logger.error(f"Konténer {container_name} logok:\n{log_output}")
                
                # Log fájlba is írjuk
                try:
                    with open(log_file, 'a', encoding='utf-8') as log_f:
                        log_f.write(f"\n--- Docker konténer logok (konténer nem fut) ---\n")
                        log_f.write(log_output)
                        log_f.write(f"\n--- Log vége ---\n")
                except Exception as e:
                    logger.warning(f"Log fájl írása sikertelen: {e}")
                
                # Konténer státusz ellenőrzése
                inspect_result = subprocess.run(
                    ["docker", "inspect", "--format", "{{.State.Status}}", container_name],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                container_status = inspect_result.stdout.strip() if inspect_result.returncode == 0 else "ismeretlen"
                
                # Exit code ellenőrzése
                exit_code_result = subprocess.run(
                    ["docker", "inspect", "--format", "{{.State.ExitCode}}", container_name],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                exit_code = exit_code_result.stdout.strip() if exit_code_result.returncode == 0 else "ismeretlen"
                
                error_msg = f"A konténer elindult, de azonnal leállt.\n"
                error_msg += f"Státusz: {container_status}\n"
                error_msg += f"Kilépési kód: {exit_code}\n"
                error_msg += f"Logok (utolsó 500 karakter):\n{log_output[-500:]}"
                
                return {
                    "success": False,
                    "message": error_msg
                }
            else:
                return {
                    "success": False,
                    "message": f"A konténer nem indult el. Docker Compose kimenet: {result.stdout}"
                }
        
        # Státusz frissítése - újrapróbálás kapcsolat hiba esetén
        max_retries = 3
        retry_count = 0
        status_updated = False
        server_id = server.id  # Mentsük el az ID-t, mert a server objektum változhat
        
        while retry_count < max_retries and not status_updated:
            try:
                if retry_count > 0:
                    # Új session létrehozása retry esetén
                    try:
                        db.rollback()
                    except:
                        pass
                    from app.database import SessionLocal
                    db = SessionLocal()
                    server = db.query(ServerInstance).filter(ServerInstance.id == server_id).first()
                    if not server:
                        break
                
                server.status = ServerStatus.RUNNING
                server.started_at = datetime.now()
                db.commit()
                status_updated = True
                logger.info(f"Szerver {server_id} státusza frissítve (próbálkozás: {retry_count + 1})")
            except Exception as db_error:
                retry_count += 1
                error_msg = str(db_error)
                if "MySQL server has gone away" in error_msg or "2006" in error_msg or "Connection reset" in error_msg:
                    logger.warning(f"Adatbázis kapcsolat hiba a szerver indításakor (próbálkozás {retry_count}/{max_retries}): {db_error}")
                    if retry_count < max_retries:
                        time.sleep(0.5 * retry_count)  # Exponenciális backoff
                        continue
                else:
                    # Más típusú hiba, nem próbáljuk újra
                    logger.error(f"Adatbázis hiba (nem kapcsolati): {db_error}")
                    break
        
        if not status_updated:
            logger.error(f"Adatbázis frissítés sikertelen {max_retries} próbálkozás után is")
            # Folytatjuk, mert a Docker indítás sikeres volt
        
        logger.info(f"Szerver {server.id} indítva Docker-rel")
        
        # Várakozás, hogy a szerver elinduljon a konténerben (3 másodperc)
        time.sleep(3)
        
        # Docker konténer logok lekérése, hogy lássuk, mi történik
        try:
            log_result = subprocess.run(
                ["docker", "logs", "--tail", "100", container_name],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            container_logs = log_result.stdout or log_result.stderr or "Nincs log kimenet"
            
            # Log fájlba is írjuk a sikeres indítást és a konténer logokat
            with open(log_file, 'a', encoding='utf-8') as log_f:
                log_f.write(f"\n--- Szerver sikeresen elindítva ---\n")
                log_f.write(f"Konténer: {container_name}\n")
                log_f.write(f"Időpont: {datetime.now().isoformat()}\n")
                log_f.write(f"\n--- Docker konténer logok (utolsó 100 sor) ---\n")
                log_f.write(container_logs)
                log_f.write(f"\n--- Log vége ---\n")
            
            # Ha a logokban van hiba, logoljuk
            if "error" in container_logs.lower() or "hiba" in container_logs.lower() or "HIBA" in container_logs:
                logger.warning(f"Konténer {container_name} logokban hiba van:\n{container_logs[-500:]}")
        except Exception as e:
            logger.warning(f"Docker logok lekérése sikertelen: {e}")
            try:
                with open(log_file, 'a', encoding='utf-8') as log_f:
                    log_f.write(f"\n--- Szerver sikeresen elindítva ---\n")
                    log_f.write(f"Konténer: {container_name}\n")
                    log_f.write(f"Időpont: {datetime.now().isoformat()}\n")
                    log_f.write(f"\n⚠️ Docker logok lekérése sikertelen: {e}\n")
            except:
                pass
        
        return {
            "success": True,
            "message": f"Szerver sikeresen elindítva Docker-rel. Log fájl: {log_file}",
            "log_file": str(log_file)
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
            try:
                server.status = ServerStatus.STOPPED
                server.started_at = None
                db.commit()
            except Exception as db_error:
                # Ha a kapcsolat megszakadt, újrapróbáljuk új session-nel
                logger.warning(f"Adatbázis kapcsolat hiba: {db_error}, újrapróbálás...")
                try:
                    db.rollback()
                    from app.database import SessionLocal
                    new_db = SessionLocal()
                    try:
                        server = new_db.query(ServerInstance).filter(ServerInstance.id == server.id).first()
                        if server:
                            server.status = ServerStatus.STOPPED
                            server.started_at = None
                            new_db.commit()
                    finally:
                        new_db.close()
                except Exception as retry_error:
                    logger.error(f"Adatbázis frissítés sikertelen: {retry_error}")
            return {
                "success": True,
                "message": "A szerver nem futott"
            }
        
        # Ellenőrizzük, hogy a konténer fut-e
        container_name = f"zedin_asa_{server.id}"
        try:
            result = subprocess.run(
                ["docker", "ps", "-q", "-f", f"name=^{container_name}$"],
                capture_output=True,
                text=True,
                timeout=5
            )
            container_running = result.returncode == 0 and result.stdout.strip()
        except Exception as e:
            logger.warning(f"Konténer ellenőrzés hiba: {e}")
            container_running = False
        
        # Ha a konténer fut, küldjük a saveworld parancsot RCON-on keresztül
        if container_running:
            try:
                # RCON beállítások lekérése
                config = server.config or {}
                rcon_enabled = config.get("RCON_ENABLED", True)
                rcon_port = server.rcon_port or 27020
                server_admin_password = config.get("SERVER_ADMIN_PASSWORD", "")
                
                if rcon_enabled and server_admin_password:
                    logger.info(f"Saveworld parancs küldése RCON-on keresztül (port: {rcon_port})...")
                    # 3 másodperces timeout-tal küldjük (mint a POK-manager.sh-ben)
                    send_rcon_command("localhost", rcon_port, server_admin_password, "saveworld", timeout=3)
                    logger.info("Saveworld parancs elküldve, várakozás 5 másodpercet...")
                    time.sleep(5)  # 5 másodperc várakozás (mint a POK-manager.sh-ben)
                else:
                    logger.info("RCON nincs engedélyezve vagy nincs admin jelszó, saveworld parancs kihagyva")
            except Exception as rcon_error:
                logger.warning(f"RCON saveworld parancs hiba (folytatjuk a leállítással): {rcon_error}")
        
        # Docker Compose leállítás
        compose_cmd = docker_compose_cmd.split() + ["-f", str(compose_file), "down"]
        
        result = subprocess.run(
            compose_cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        # Státusz frissítése - újrapróbálás kapcsolat hiba esetén
        max_retries = 5
        retry_count = 0
        status_updated = False
        server_id = server.id  # Mentsük el az ID-t, mert a server objektum változhat
        
        # Zárjuk be az eredeti session-t, hogy ne legyen problémás kapcsolat
        try:
            db.close()
        except:
            pass
        
        while retry_count < max_retries and not status_updated:
            try:
                # Mindig új session-t hozunk létre, hogy biztosan működjön
                try:
                    if retry_count > 0:
                        # Várakozás retry esetén
                        time.sleep(0.5 * retry_count)  # Exponenciális backoff
                except:
                    pass
                
                from app.database import SessionLocal
                new_db = SessionLocal()
                try:
                    # Új session-ben lekérjük a szervert
                    server = new_db.query(ServerInstance).filter(ServerInstance.id == server_id).first()
                    if not server:
                        logger.warning(f"Szerver {server_id} nem található az adatbázisban")
                        new_db.close()
                        break
                    
                    server.status = ServerStatus.STOPPED
                    server.started_at = None
                    new_db.commit()
                    status_updated = True
                    logger.info(f"Szerver {server_id} státusza frissítve (próbálkozás: {retry_count + 1})")
                    new_db.close()
                except Exception as inner_error:
                    new_db.rollback()
                    new_db.close()
                    raise inner_error
                    
            except Exception as db_error:
                retry_count += 1
                error_msg = str(db_error)
                if "MySQL server has gone away" in error_msg or "2006" in error_msg or "Connection reset" in error_msg or "Lost connection" in error_msg:
                    logger.warning(f"Adatbázis kapcsolat hiba a szerver leállításakor (próbálkozás {retry_count}/{max_retries}): {db_error}")
                    if retry_count < max_retries:
                        continue
                    else:
                        logger.error(f"Adatbázis frissítés sikertelen {max_retries} próbálkozás után is")
                else:
                    # Más típusú hiba, nem próbáljuk újra
                    logger.error(f"Adatbázis hiba (nem kapcsolati): {db_error}")
                    break
        
        if not status_updated:
            logger.error(f"Adatbázis frissítés sikertelen {max_retries} próbálkozás után is")
            # Folytatjuk, mert a Docker leállítás sikeres volt
        
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
    Először saveworld parancsot küld, vár 10 másodpercet, majd leállítja és újraindítja
    
    Args:
        server: ServerInstance objektum
        db: Database session
    
    Returns:
        Dict az eredménnyel
    """
    try:
        # Ellenőrizzük, hogy a konténer fut-e
        container_name = f"zedin_asa_{server.id}"
        try:
            result = subprocess.run(
                ["docker", "ps", "-q", "-f", f"name=^{container_name}$"],
                capture_output=True,
                text=True,
                timeout=5
            )
            container_running = result.returncode == 0 and result.stdout.strip()
        except Exception as e:
            logger.warning(f"Konténer ellenőrzés hiba: {e}")
            container_running = False
        
        # Ha a konténer fut, küldjük a saveworld parancsot RCON-on keresztül
        if container_running:
            try:
                # RCON beállítások lekérése
                config = server.config or {}
                rcon_enabled = config.get("RCON_ENABLED", True)
                rcon_port = server.rcon_port or 27020
                server_admin_password = config.get("SERVER_ADMIN_PASSWORD", "")
                
                if rcon_enabled and server_admin_password:
                    logger.info(f"Saveworld parancs küldése RCON-on keresztül (port: {rcon_port}) restart előtt...")
                    # 3 másodperces timeout-tal küldjük (mint a POK-manager.sh-ben)
                    send_rcon_command("localhost", rcon_port, server_admin_password, "saveworld", timeout=3)
                    logger.info("Saveworld parancs elküldve, várakozás 5 másodpercet...")
                    time.sleep(5)  # 5 másodperc várakozás (mint a POK-manager.sh-ben)
                else:
                    logger.info("RCON nincs engedélyezve vagy nincs admin jelszó, saveworld parancs kihagyva")
            except Exception as rcon_error:
                logger.warning(f"RCON saveworld parancs hiba (folytatjuk a restart-tal): {rcon_error}")
        
        # Először leállítjuk
        stop_result = stop_server(server, db)
        if not stop_result["success"]:
            return stop_result
        
        # Várakozás (2 másodperc)
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

def update_start_command_file(server: ServerInstance, compose_file: Path, compose_data: dict) -> None:
    """
    Indítási parancs fájl létrehozása/frissítése, ami tartalmazza a tényleges ARK szerver indítási parancsot
    Ez a fájl csak akkor változik, ha a beállítások változnak
    
    Args:
        server: ServerInstance objektum
        compose_file: Docker Compose fájl útvonala
        compose_data: Docker Compose adatok
    """
    try:
        instance_dir = get_instance_dir(server)
        command_file = instance_dir / "start_command.txt"
        
        # Environment változók összegyűjtése és értelmezése
        env_vars = compose_data.get('services', {}).get('asaserver', {}).get('environment', [])
        env_dict = {}
        for env_var in env_vars:
            if '=' in env_var:
                key, value = env_var.split('=', 1)
                env_dict[key] = value
        
        # Szerver beállítások kiolvasása
        map_name = env_dict.get('MAP_NAME', 'TheIsland')
        # Map név _WP utótag hozzáadása, ha nincs
        if not map_name.endswith('_WP'):
            map_name_wp = f"{map_name}_WP"
        else:
            map_name_wp = map_name
        
        session_name = env_dict.get('SESSION_NAME', server.name)
        # Ha "Server_name" van beállítva (placeholder), akkor használjuk a server.name-t
        if session_name == "Server_name" or session_name == "server_name":
            session_name = server.name
        asa_port = env_dict.get('ASA_PORT', str(server.port or 7777))
        query_port = env_dict.get('QUERY_PORT', str(server.query_port or int(asa_port) + 2))
        rcon_port = env_dict.get('RCON_PORT', str(server.rcon_port or 27015))
        max_players = env_dict.get('MAX_PLAYERS', str(server.max_players or 70))
        rcon_enabled = env_dict.get('RCON_ENABLED', 'True')
        server_admin_password = env_dict.get('SERVER_ADMIN_PASSWORD', '')
        server_password = env_dict.get('SERVER_PASSWORD', '')
        battleeye = env_dict.get('BATTLEEYE', 'False')
        mod_ids = env_dict.get('MOD_IDS', '')
        custom_server_args = env_dict.get('CUSTOM_SERVER_ARGS', '')
        
        # Debug: logoljuk az értékeket
        logger.info(f"DEBUG: Indítási parancs generálás - server_admin_password: '{server_admin_password}' (type: {type(server_admin_password)}, len: {len(server_admin_password) if server_admin_password else 0})")
        logger.info(f"DEBUG: env_dict keys: {list(env_dict.keys())}")
        logger.info(f"DEBUG: SERVER_ADMIN_PASSWORD in env_dict: {'SERVER_ADMIN_PASSWORD' in env_dict}")
        
        # Cluster ID lekérése
        cluster_id = ''
        if server.cluster:
            cluster_id = server.cluster.cluster_id
        
        # ARK szerver indítási parancs összeállítása
        # Formátum: MapName_WP?listen?SessionName="..."?RCONEnabled=True?RCONPort=...?ServerAdminPassword=... -Port=... -QueryPort=... -WinLiveMaxPlayers=... -clusterid=... -servergamelog -servergamelogincludetribelogs -ServerRCONOutputTribeLogs -mods=... -NoBattlEye -passivemods=...
        
        # Query string összeállítása: ?listen?SessionName="..."?RCONEnabled=...?RCONPort=...?ServerAdminPassword=...
        query_params = []
        query_params.append('listen')
        query_params.append(f'SessionName="{session_name}"')
        
        if rcon_enabled == 'True':
            query_params.append('RCONEnabled=True')
            query_params.append(f'RCONPort={rcon_port}')
        
        # ServerAdminPassword mindig szerepeljen, ha van értéke (függetlenül az RCON állapotától)
        if server_admin_password and server_admin_password.strip():
            query_params.append(f'ServerAdminPassword={server_admin_password}')
            logger.info(f"DEBUG: ServerAdminPassword hozzáadva a query_params-hoz: {server_admin_password}")
        else:
            logger.warning(f"DEBUG: ServerAdminPassword NEM került hozzáadásra! Érték: '{server_admin_password}' (üres: {not server_admin_password or not server_admin_password.strip()})")
        
        if server_password:
            query_params.append(f'ServerPassword={server_password}')
        
        # Query string összeállítása
        query_string = '?' + '?'.join(query_params)
        
        # Teljes parancs összeállítása
        command_parts = []
        
        # Első rész: MapName_WP?listen?SessionName=...?RCONEnabled=...?RCONPort=...?ServerAdminPassword=...
        first_part = f'{map_name_wp}{query_string}'
        command_parts.append(first_part)
        
        # Második rész: -Port=... -QueryPort=... -WinLiveMaxPlayers=... -clusterid=...
        second_part_parts = []
        second_part_parts.append(f'-Port={asa_port}')
        second_part_parts.append(f'-QueryPort={query_port}')
        second_part_parts.append(f'-WinLiveMaxPlayers={max_players}')
        
        if cluster_id:
            second_part_parts.append(f'-clusterid={cluster_id}')
        
        second_part = ' '.join(second_part_parts)
        command_parts.append(second_part)
        
        # Harmadik rész: -servergamelog -servergamelogincludetribelogs -ServerRCONOutputTribeLogs -NoBattlEye -mods=... -passivemods=... custom args
        third_part_parts = []
        
        # Log argumentumok (mindig szerepeljenek)
        third_part_parts.append('-servergamelog')
        third_part_parts.append('-servergamelogincludetribelogs')
        third_part_parts.append('-ServerRCONOutputTribeLogs')
        
        if battleeye == 'True':
            third_part_parts.append('-UseBattlEye')
        else:
            third_part_parts.append('-NoBattlEye')
        
        # Aktív modok - helyes formátum: -mods=123456,789012
        if mod_ids:
            third_part_parts.append(f'-mods={mod_ids}')
        
        # Passzív modok - helyes formátum: -passivemods=123456,789012
        passive_mods = env_dict.get('PASSIVE_MODS', '')
        if passive_mods:
            third_part_parts.append(f'-passivemods={passive_mods}')
        
        if custom_server_args:
            third_part_parts.append(custom_server_args)
        
        if third_part_parts:
            third_part = ' '.join(third_part_parts)
            command_parts.append(third_part)
        
        # Teljes parancs összeállítása (egy hosszú sor, mint a példában)
        # Formátum: MapName_WP?listen?SessionName="..."?RCONEnabled=True?RCONPort=...?ServerAdminPassword=... -Port=... -QueryPort=... -WinLiveMaxPlayers=... -clusterid=... -servergamelog -servergamelogincludetribelogs -ServerRCONOutputTribeLogs -mods=... -NoBattlEye -passivemods=...
        full_command = ' '.join(command_parts)
        
        # Parancs fájl írása
        command_lines = [
            f"# ARK Survival Ascended Server Indítási Parancs",
            f"# Szerver ID: {server.id}",
            f"# Ez a parancs csak akkor változik, ha a beállítások változnak",
            "",
            full_command,
        ]
        
        # Fájl írása
        with open(command_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(command_lines))
        
        logger.info(f"Indítási parancs fájl frissítve: {command_file}")
    except Exception as e:
        logger.warning(f"Hiba az indítási parancs fájl létrehozásakor: {e}")
        import traceback
        traceback.print_exc()

def get_start_command_string(server: ServerInstance, db: Session) -> Optional[str]:
    """
    Szerver indítási parancs string formában (megjelenítéshez)
    A parancsot a start_command.txt fájlból olvassa be, ami csak akkor változik, ha a beállítások változnak
    A teljes fájlt adja vissza, hogy minden argumentum látható legyen
    
    Args:
        server: ServerInstance objektum
        db: Database session
    
    Returns:
        String formában a teljes parancs argumentumokkal vagy None
    """
    try:
        instance_dir = get_instance_dir(server)
        command_file = instance_dir / "start_command.txt"
        compose_file = get_docker_compose_file(server)
        
        # Ha létezik a compose fájl, mindig frissítsük az indítási parancs fájlt
        if compose_file.exists():
            try:
                # Docker Compose fájl beolvasása
                with open(compose_file, 'r', encoding='utf-8') as f:
                    compose_data = yaml.safe_load(f)
                
                # FONTOS: Ha a Docker Compose fájlban nincs SERVER_ADMIN_PASSWORD, de a server.config-ban van,
                # akkor hozzáadjuk a compose_data-hoz, hogy az indítási parancs generálásnál használható legyen
                if compose_data and 'services' in compose_data and 'asaserver' in compose_data['services']:
                    env_list = compose_data['services']['asaserver'].get('environment', [])
                    has_admin_password = any('SERVER_ADMIN_PASSWORD=' in str(env) for env in env_list)
                    
                    if not has_admin_password and server.config:
                        admin_password = server.config.get("ServerAdminPassword", "")
                        if admin_password:
                            if isinstance(env_list, list):
                                env_list.append(f'SERVER_ADMIN_PASSWORD={admin_password}')
                                logger.info(f"DEBUG: SERVER_ADMIN_PASSWORD hozzáadva a compose_data-hoz server.config-ból: {admin_password[:3]}...")
                            else:
                                logger.warning(f"DEBUG: env_list nem lista típusú: {type(env_list)}")
                
                # Frissítsük az indítási parancs fájlt
                if compose_data:
                    update_start_command_file(server, compose_file, compose_data)
            except Exception as e:
                logger.warning(f"Hiba az indítási parancs fájl frissítésekor: {e}")
                import traceback
                traceback.print_exc()
        
        # Most olvassuk be a fájlt (frissített vagy meglévő)
        if command_file.exists():
            with open(command_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    return content
        
        # Ha nincs fájl, generáljuk a parancsot
        docker_compose_cmd = get_docker_compose_cmd()
        if not docker_compose_cmd:
            return None
        
        if not compose_file.exists():
            return None
        
        # Docker Compose parancs
        cmd = f"{docker_compose_cmd} -f {compose_file} up -d"
        return cmd
    except Exception as e:
        logger.error(f"Hiba a parancs generálásakor: {e}")
        import traceback
        traceback.print_exc()
        return None

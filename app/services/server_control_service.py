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
    A konfigurációkat a Saved/Config/WindowsServer mappából olvassa be
    
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
                config_values["SESSION_NAME"] = session_settings.get("SessionName") or server_settings.get("SessionName") or server.name
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
        
        # Portok
        port = server.port or settings.ark_default_port
        query_port = server.query_port or (port + 2)
        rcon_port = server.rcon_port or settings.ark_default_rcon_port
        
        # Docker image és útvonalak meghatározása
        use_custom_image = getattr(settings, 'ark_docker_use_custom', False)
        docker_image = getattr(settings, 'ark_docker_image', 'acekorneya/asa_server:2_1_latest')
        
        if use_custom_image:
            # Saját Docker image: /home/zedin/arkserver struktúra
            container_work_dir = '/home/zedin/arkserver'
            container_saved_path = '/home/zedin/arkserver/ShooterGame/Saved'
        else:
            # POK Docker image: /home/pok/arkserver struktúra
            container_work_dir = '/home/pok/arkserver'
            container_saved_path = '/home/pok/arkserver/ShooterGame/Saved'
        
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
                    ],
                }
            }
        }
        
        # Server Admin Password
        if config_values.get("ServerAdminPassword"):
            compose_data['services']['asaserver']['environment'].append(
                f'SERVER_ADMIN_PASSWORD={config_values.get("ServerAdminPassword")}'
            )
        
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
        
        # Custom Server Args
        config = server.config or {}
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
                    # Ellenőrizzük a Linux binárist
                    linux_binary = binaries_path / "Linux" / "ShooterGameServer"
                    # Ellenőrizzük a Windows binárist is
                    win64_binary = binaries_path / "Win64" / "ShooterGameServer.exe"
                    
                    # Nézzük meg, mi van a Binaries mappában
                    binaries_contents = [item.name for item in binaries_path.iterdir()] if binaries_path.exists() else []
                    logger.info(f"Binaries mappa tartalma: {binaries_contents}")
                    
                    if linux_binary.exists():
                        logger.info(f"Linux ShooterGameServer bináris megtalálva: {linux_binary}")
                    elif win64_binary.exists():
                        logger.info(f"Windows ShooterGameServer bináris megtalálva: {win64_binary} (Wine-nal fog futni)")
                    else:
                        logger.warning(f"ShooterGameServer bináris nem található (sem Linux, sem Windows):")
                        logger.warning(f"  - Linux: {linux_binary}")
                        logger.warning(f"  - Windows: {win64_binary}")
                        logger.warning(f"  - Binaries mappa tartalma: {binaries_contents}")
                        if binaries_path.exists():
                            # Nézzük meg részletesebben, mi van a Binaries mappában
                            for item in binaries_path.iterdir():
                                if item.is_dir():
                                    sub_contents = [subitem.name for subitem in item.iterdir()] if item.exists() else []
                                    logger.warning(f"  - {item.name}/ tartalma: {sub_contents[:10]}")
        
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
        
        # Docker Compose fájl létrehozása/frissítése
        # Mindig frissítjük, hogy a konfigurációk szinkronban legyenek
        compose_file = get_docker_compose_file(server)
        if not create_docker_compose_file(server, serverfiles_link, saved_path):
            return {
                "success": False,
                "message": "Docker Compose fájl létrehozása/frissítése sikertelen"
            }
        
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
            error_msg = result.stderr or result.stdout or "Ismeretlen hiba"
            return {
                "success": False,
                "message": f"Docker Compose indítás sikertelen: {error_msg}"
            }
        
        # Várakozás, hogy a konténer elinduljon (2 másodperc)
        import time
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
                from datetime import datetime
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
                        import time
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
        
        # Docker Compose leállítás
        compose_cmd = docker_compose_cmd.split() + ["-f", str(compose_file), "down"]
        
        result = subprocess.run(
            compose_cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        
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
                
                server.status = ServerStatus.STOPPED
                server.started_at = None
                db.commit()
                status_updated = True
                logger.info(f"Szerver {server_id} státusza frissítve (próbálkozás: {retry_count + 1})")
            except Exception as db_error:
                retry_count += 1
                error_msg = str(db_error)
                if "MySQL server has gone away" in error_msg or "2006" in error_msg or "Connection reset" in error_msg:
                    logger.warning(f"Adatbázis kapcsolat hiba a szerver leállításakor (próbálkozás {retry_count}/{max_retries}): {db_error}")
                    if retry_count < max_retries:
                        import time
                        time.sleep(0.5 * retry_count)  # Exponenciális backoff
                        continue
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
        session_name = env_dict.get('SESSION_NAME', server.name)
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
        
        # Cluster ID lekérése
        cluster_id = ''
        if server.cluster:
            cluster_id = server.cluster.cluster_id
        
        # ARK szerver indítási parancs összeállítása (hasonló a képen láthatóhoz)
        # Formátum: ArkAscendedServer.exe MapName ?listen?SessionName="..."?RCONEnabled=True?RCONPort=...?ServerAdminPassword=... -Port=... -QueryPort=... -WinLiveMaxPlayers=... -clusterid=... -ActiveMods=...
        
        # ?listen?SessionName="..."?RCONEnabled=...?RCONPort=...?ServerAdminPassword=...
        query_params = []
        query_params.append('listen')
        query_params.append(f'SessionName="{session_name}"')
        
        if rcon_enabled == 'True':
            query_params.append('RCONEnabled=True')
            query_params.append(f'RCONPort={rcon_port}')
            if server_admin_password:
                query_params.append(f'ServerAdminPassword={server_admin_password}')
        
        if server_password:
            query_params.append(f'ServerPassword={server_password}')
        
        # Query string összeállítása
        query_string = '?' + '?'.join(query_params)
        
        # Teljes parancs összeállítása (hosszú sor, mint a képen)
        command_parts = []
        
        # Első rész: ArkAscendedServer.exe MapName ?listen?SessionName=...?RCONEnabled=...?RCONPort=...?ServerAdminPassword=...
        first_part = f'ArkAscendedServer.exe {map_name}{query_string}'
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
        
        # Harmadik rész: -UseBattlEye -ActiveMods=... custom args
        third_part_parts = []
        
        if battleeye == 'True':
            third_part_parts.append('-UseBattlEye')
        
        if mod_ids:
            third_part_parts.append(f'-ActiveMods={mod_ids}')
        
        if custom_server_args:
            third_part_parts.append(custom_server_args)
        
        if third_part_parts:
            third_part = ' '.join(third_part_parts)
            command_parts.append(third_part)
        
        # Teljes parancs összeállítása (egy hosszú sor, mint a képen)
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
        
        # Ha létezik a fájl, olvassuk be a teljes tartalmat
        if command_file.exists():
            with open(command_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    return content
        
        # Ha nincs fájl, generáljuk a parancsot
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

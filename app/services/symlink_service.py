"""
Symlink kezelő szolgáltatás - szerverfájlok symlink kezelése
"""

import os
import shutil
from pathlib import Path
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.config import settings
from app.database import ArkServerFiles, SessionLocal

def get_user_serverfiles_path(user_id: int) -> Path:
    """
    Felhasználó serverfiles mappa útvonala (régi struktúra, kompatibilitás)
    
    Args:
        user_id: User ID (Server Admin)
    
    Returns:
        Path objektum a felhasználó serverfiles mappájához
    """
    base_path = Path(settings.ark_serverfiles_base)
    user_serverfiles_path = base_path / f"user_{user_id}"
    return user_serverfiles_path

def get_servers_base_path() -> Path:
    """
    Servers mappa alap útvonala (új struktúra)
    
    Returns:
        Path objektum a Servers mappához
    """
    if hasattr(settings, 'ark_serverfiles_base') and settings.ark_serverfiles_base:
        base_dir = Path(settings.ark_serverfiles_base).parent
    else:
        base_dir = Path("/home/ai_developer/ZedinSteamManager/Server/ArkAscended")
    
    servers_base = base_dir / "Servers"
    return servers_base

def get_server_path(server_id: Optional[int], cluster_id: Optional[str] = None, user_id: Optional[int] = None) -> Path:
    """
    Szerver útvonal generálása (új struktúra: Servers/server_{server_id}/)
    
    Args:
        server_id: Szerver ID
        cluster_id: Cluster ID (opcionális, csak kompatibilitás miatt)
        user_id: User ID (opcionális, új struktúrában nem használjuk)
    
    Returns:
        Path objektum a szerver útvonalához
    """
    if not server_id:
        return None
    
    # Új struktúra: Servers/server_{server_id}/
    servers_base = get_servers_base_path()
    server_path = servers_base / f"server_{server_id}"
    
    return server_path

def get_active_ark_files(db: Session) -> Optional[ArkServerFiles]:
    """Aktív Ark szerverfájlok lekérése (Manager Admin)"""
    return db.query(ArkServerFiles).filter(
        ArkServerFiles.is_active == True
    ).first()

def get_active_user_serverfiles(db: Session, user_id: int) -> Optional[Path]:
    """
    Aktív felhasználó szerverfájlok útvonala
    
    Args:
        db: Adatbázis session
        user_id: User ID (Server Admin)
    
    Returns:
        Path objektum az aktív szerverfájlok útvonalához vagy None
    """
    from app.database import UserServerFiles
    serverfiles = db.query(UserServerFiles).filter(
        and_(
            UserServerFiles.user_id == user_id,
            UserServerFiles.is_active == True,
            UserServerFiles.installation_status == "completed"
        )
    ).first()
    
    if serverfiles:
        install_path = Path(serverfiles.install_path)
        if install_path.exists():
            return install_path
    
    return None

def create_server_symlink(server_id: Optional[int], cluster_id: Optional[str] = None, db: Session = None) -> Optional[Path]:
    """
    Symlink létrehozása a szerverhez (felhasználó serverfiles mappában)
    
    Args:
        server_id: Szerver ID
        cluster_id: Cluster ID (opcionális, csak kompatibilitás miatt)
        db: Adatbázis session
    
    Returns:
        Path objektum a symlink útvonalához vagy None
    """
    if db is None:
        db = SessionLocal()
        should_close = True
    else:
        should_close = False
    
    try:
        # Server instance lekérése a user_id-hoz
        from app.database import ServerInstance
        server_instance = db.query(ServerInstance).filter(
            ServerInstance.id == server_id
        ).first()
        
        if not server_instance:
            return None
        
        # Aktív felhasználó szerverfájlok lekérése
        install_path = get_active_user_serverfiles(db, server_instance.server_admin_id)
        if not install_path:
            # Fallback: Manager Admin szerverfájlok
            ark_files = get_active_ark_files(db)
            if not ark_files:
                return None
            install_path = Path(ark_files.install_path)
            if not install_path.exists():
                return None
        
        # Új struktúra: Servers/server_{server_id}/
        servers_base = get_servers_base_path()
        server_path = servers_base / f"server_{server_id}"
        
        # Szülő könyvtárak létrehozása
        server_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Ha már létezik, töröljük
        if server_path.exists() or server_path.is_symlink():
            if server_path.is_symlink():
                server_path.unlink()
            else:
                shutil.rmtree(server_path)
        
        # Szerver mappa létrehozása
        server_path.mkdir(parents=True, exist_ok=True)
        
        # ServerFiles symlink létrehozása az aktív Ark fájlokhoz
        serverfiles_link = server_path / "ServerFiles"
        if serverfiles_link.exists() or serverfiles_link.is_symlink():
            if serverfiles_link.is_symlink():
                serverfiles_link.unlink()
            else:
                shutil.rmtree(serverfiles_link)
        serverfiles_link.symlink_to(install_path)
        
        # Dedikált Saved mappa létrehozása és symlink
        # A server_path most már a Servers/server_{server_id}/ mappa
        # A Saved mappa közvetlenül ebben lesz: Servers/server_{server_id}/Saved/
        create_dedicated_saved_folder(serverfiles_link)  # A symlink-et adjuk át, hogy a Saved symlink a helyes helyre kerüljön
        
        # Alapértelmezett konfigurációs fájlok másolása
        copy_default_config_files(serverfiles_link)
        
        return serverfiles_link  # Visszaadjuk a ServerFiles symlink-et, hogy kompatibilis maradjon
    finally:
        if should_close:
            db.close()

def remove_server_symlink(server_id: int, cluster_id: Optional[str] = None) -> bool:
    """
    Symlink törlése és a dedikált config mappa törlése
    
    Args:
        server_id: Szerver ID
        cluster_id: Cluster ID (opcionális)
    
    Returns:
        True ha sikeres, False egyébként
    """
    try:
        # Először megkeressük a szerver útvonalát
        # Ehhez szükségünk van a user_id-ra, amit az adatbázisból kell lekérni
        from app.database import ServerInstance, SessionLocal
        db = SessionLocal()
        try:
            server_instance = db.query(ServerInstance).filter(ServerInstance.id == server_id).first()
            if not server_instance:
                return False
            
            # Új struktúra: Servers/server_{server_id}/
            servers_base = get_servers_base_path()
            server_path = servers_base / f"server_{server_id}"
        finally:
            db.close()
        
        # Új struktúra: Servers/server_{server_id}/ teljes mappa törlése
        if server_path.exists():
            # Saved symlink törlése (ha létezik) - a ServerFiles symlink mögött
            serverfiles_link = server_path / "ServerFiles"
            if serverfiles_link.exists() and serverfiles_link.is_symlink():
                real_saved_path = get_server_saved_path(serverfiles_link)
                if real_saved_path.exists() and real_saved_path.is_symlink():
                    try:
                        real_saved_path.unlink()
                        print(f"Saved symlink törölve: {real_saved_path}")
                    except Exception as e:
                        print(f"Figyelmeztetés: Saved symlink törlése sikertelen: {e}")
                
                # Config symlink törlése (ha létezik)
                real_config_path = get_server_config_path(serverfiles_link)
                if real_config_path.exists() and real_config_path.is_symlink():
                    try:
                        real_config_path.unlink()
                        print(f"Config symlink törölve: {real_config_path}")
                    except Exception as e:
                        print(f"Figyelmeztetés: Config symlink törlése sikertelen: {e}")
            
            # Teljes szerver mappa törlése (Saved, ServerFiles symlink, stb. mind benne van)
            try:
                shutil.rmtree(server_path)
                print(f"Szerver mappa törölve: {server_path}")
            except Exception as e:
                print(f"Figyelmeztetés: Szerver mappa törlése sikertelen: {e}")
            return True
        
        return False
    except Exception as e:
        print(f"Hiba a symlink törlésekor: {e}")
        import traceback
        traceback.print_exc()
        return False

def get_server_config_path(server_path: Path) -> Path:
    """Szerver konfigurációs fájl útvonala (a symlink mögötti tényleges útvonal)"""
    if server_path.is_symlink():
        real_server_path = server_path.resolve()
    else:
        real_server_path = server_path
    return real_server_path / "ShooterGame" / "Saved" / "Config" / "WindowsServer"

def get_server_dedicated_config_path(server_path: Path) -> Path:
    """
    Szerver dedikált konfigurációs mappa útvonala (külön a symlink-től)
    Ez a mappa minden szerverhez külön van, nem osztott
    
    Args:
        server_path: Szerver útvonal (symlink)
    
    Returns:
        Path objektum a dedikált config mappához
    """
    # A dedikált config mappa a symlink mappájában van, de külön mappaként
    # Példa: user_1/server_5 -> user_1/server_5_config
    dedicated_config_path = server_path.parent / f"{server_path.name}_config"
    return dedicated_config_path

def get_server_dedicated_saved_path(server_path: Path) -> Path:
    """
    Szerver dedikált Saved mappa útvonala (új struktúra: Servers/server_{server_id}/Saved/)
    Ez a mappa minden szerverhez külön van, nem osztott
    
    Args:
        server_path: Szerver útvonal (ServerFiles symlink vagy szerver mappa)
    
    Returns:
        Path objektum a dedikált Saved mappához
    """
    # Új struktúra: 
    # Ha server_path egy symlink (ServerFiles), akkor a parent a szerver mappa
    # Ha server_path egy mappa (Servers/server_{server_id}/), akkor közvetlenül használjuk
    if server_path.is_symlink() or server_path.name == "ServerFiles":
        # ServerFiles symlink esetén: Servers/server_{server_id}/ServerFiles -> Servers/server_{server_id}/Saved/
        server_dir = server_path.parent
    else:
        # Ha már a szerver mappa: Servers/server_{server_id}/ -> Servers/server_{server_id}/Saved/
        server_dir = server_path
    
    dedicated_saved_path = server_dir / "Saved"
    return dedicated_saved_path

def get_server_saved_path(server_path: Path) -> Path:
    """
    Szerver Saved mappa útvonala (a symlink mögötti tényleges útvonal)
    Ez a symlink-et követi, ami a dedikált Saved mappára mutat
    
    Args:
        server_path: Szerver útvonal (symlink)
    
    Returns:
        Path objektum a Saved mappához
    """
    if server_path.is_symlink():
        real_server_path = server_path.resolve()
    else:
        real_server_path = server_path
    return real_server_path / "ShooterGame" / "Saved"

def create_dedicated_saved_folder(serverfiles_link: Path) -> bool:
    """
    Dedikált Saved mappa létrehozása és symlink beállítása
    Új struktúra: Servers/server_{server_id}/Saved/
    
    Args:
        serverfiles_link: ServerFiles symlink útvonala (Servers/server_{server_id}/ServerFiles)
    
    Returns:
        True ha sikeres, False egyébként
    """
    try:
        # Új struktúra: Servers/server_{server_id}/Saved/
        server_dir = serverfiles_link.parent  # Servers/server_{server_id}/
        dedicated_saved_path = server_dir / "Saved"
        
        # Ha már létezik a dedikált Saved mappa, ne töröljük (megtartjuk a meglévő adatokat)
        if not dedicated_saved_path.exists():
            # Saved mappa létrehozása
            dedicated_saved_path.mkdir(parents=True, exist_ok=True)
            
            # Alapmappák létrehozása
            (dedicated_saved_path / "Config").mkdir(exist_ok=True)
            (dedicated_saved_path / "Config" / "WindowsServer").mkdir(exist_ok=True)
            (dedicated_saved_path / "SavedArks").mkdir(exist_ok=True)
            (dedicated_saved_path / "Logs").mkdir(exist_ok=True)
            
            print(f"Dedikált Saved mappa létrehozva: {dedicated_saved_path}")
        else:
            print(f"Dedikált Saved mappa már létezik, megtartjuk a meglévő adatokat: {dedicated_saved_path}")
        
        # Tényleges szerver Saved mappa útvonala (a ServerFiles symlink mögött)
        real_saved_path = get_server_saved_path(serverfiles_link)
        real_saved_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Ha már létezik Saved mappa vagy symlink, töröljük
        if real_saved_path.exists() or real_saved_path.is_symlink():
            if real_saved_path.is_symlink():
                real_saved_path.unlink()
            else:
                # Ha mappa, akkor csak a tartalmát töröljük, ne az egész mappát
                # (mert lehet, hogy más fájlok is vannak benne)
                for item in real_saved_path.iterdir():
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
        
        # Symlink létrehozása: a tényleges szerver Saved mappája -> dedikált Saved mappa
        # Ha már létezik a symlink, ellenőrizzük, hogy helyes-e
        if real_saved_path.exists() or real_saved_path.is_symlink():
            if real_saved_path.is_symlink():
                # Ha már symlink, ellenőrizzük, hogy a cél helyes-e
                current_target = real_saved_path.readlink()
                if current_target == dedicated_saved_path:
                    print(f"Saved mappa symlink már létezik és helyes: {real_saved_path} -> {dedicated_saved_path}")
                    return True
                else:
                    # Ha rossz célra mutat, töröljük és újra létrehozzuk
                    print(f"Saved mappa symlink rossz célra mutat, törlés és újralétrehozás...")
                    real_saved_path.unlink()
            else:
                # Ha nem symlink, de létezik, akkor töröljük (nem kellene itt lennie)
                print(f"Saved mappa nem symlink, de létezik, törlés...")
                if real_saved_path.is_dir():
                    import shutil
                    shutil.rmtree(real_saved_path)
                else:
                    real_saved_path.unlink()
        
        real_saved_path.symlink_to(dedicated_saved_path)
        
        print(f"Saved mappa symlink létrehozva/frissítve: {real_saved_path} -> {dedicated_saved_path}")
        return True
    except Exception as e:
        print(f"Hiba a dedikált Saved mappa létrehozásakor: {e}")
        import traceback
        traceback.print_exc()
        return False

def get_default_config_path() -> Path:
    """Alapértelmezett konfigurációs fájlok útvonala"""
    return Path("/home/ai_developer/ZedinSteamManager/Server/ArkAscended/defaults")

def copy_default_config_files(serverfiles_link: Path) -> bool:
    """
    Alapértelmezett konfigurációs fájlok másolása a szerverhez
    Új struktúra: Servers/server_{server_id}/Saved/Config/WindowsServer/
    
    Args:
        serverfiles_link: ServerFiles symlink útvonala (Servers/server_{server_id}/ServerFiles)
    
    Returns:
        True ha sikeres, False egyébként
    """
    try:
        default_config_path = get_default_config_path()
        
        # Ellenőrizzük, hogy létezik-e a defaults mappa
        if not default_config_path.exists():
            print(f"Figyelmeztetés: Alapértelmezett config mappa nem található: {default_config_path}")
            return False
        
        # Új struktúra: Servers/server_{server_id}/Saved/Config/WindowsServer/
        server_dir = serverfiles_link.parent  # Servers/server_{server_id}/
        dedicated_saved_path = server_dir / "Saved"
        dedicated_config_in_saved = dedicated_saved_path / "Config" / "WindowsServer"
        
        # Ha már létezik a dedikált Saved mappa és van benne config, ne másoljuk újra (megtartjuk a meglévő beállításokat)
        config_already_exists = dedicated_config_in_saved.exists() and any(dedicated_config_in_saved.iterdir())
        
        if not config_already_exists:
            # Config mappa létrehozása a Saved mappában, ha nem létezik
            dedicated_config_in_saved.mkdir(parents=True, exist_ok=True)
            
            # Alapértelmezett fájlok másolása
            if default_config_path.is_dir():
                # Rekurzív másolás a defaults mappából
                for item in default_config_path.iterdir():
                    dest_item = dedicated_config_in_saved / item.name
                    
                    if item.is_dir():
                        # Mappa másolása
                        if dest_item.exists():
                            shutil.rmtree(dest_item)
                        shutil.copytree(item, dest_item)
                    else:
                        # Fájl másolása
                        shutil.copy2(item, dest_item)
                
                print(f"Alapértelmezett config fájlok másolva: {default_config_path} -> {dedicated_config_in_saved}")
            else:
                print(f"Figyelmeztetés: Alapértelmezett config útvonal nem mappa: {default_config_path}")
        else:
            print(f"Dedikált config mappa már létezik, megtartjuk a meglévő beállításokat: {dedicated_config_in_saved}")
        
        # Mindig létrehozzuk/frissítjük a symlink-et a dedikált config mappából a tényleges szerver config mappájába
        # A config mappa a dedikált Saved mappában van (dedicated_saved_path/Config/WindowsServer)
        # De a tényleges szerver Saved mappája symlink, szóval a config mappa is a symlink mögött lesz
        real_saved_path = get_server_saved_path(serverfiles_link)
        real_config_path = real_saved_path / "Config" / "WindowsServer"
        
        # A symlink mögött nem lehet mappát létrehozni, csak a dedikált Saved mappában
        # A Config mappát a dedikált Saved mappában hozzuk létre (ha még nincs)
        dedicated_config_path = dedicated_saved_path / "Config" / "WindowsServer"
        if not dedicated_config_path.exists():
            dedicated_config_path.mkdir(parents=True, exist_ok=True)
        
        # Ha már létezik config mappa vagy symlink, töröljük
        if real_config_path.exists() or real_config_path.is_symlink():
            if real_config_path.is_symlink():
                real_config_path.unlink()
            else:
                # Ha mappa, akkor csak a tartalmát töröljük, ne az egész mappát
                # (mert lehet, hogy más fájlok is vannak benne)
                for item in real_config_path.iterdir():
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
        
        # Symlink létrehozása: a tényleges szerver config mappája -> dedikált Saved mappában lévő config mappa
        real_config_path.symlink_to(dedicated_config_in_saved)
        
        print(f"Config symlink létrehozva/frissítve: {real_config_path} -> {dedicated_config_in_saved}")
        return True
    except Exception as e:
        print(f"Hiba az alapértelmezett config fájlok másolásakor: {e}")
        import traceback
        traceback.print_exc()
        return False


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
    Felhasználó serverfiles mappa útvonala
    
    Args:
        user_id: User ID (Server Admin)
    
    Returns:
        Path objektum a felhasználó serverfiles mappájához
    """
    base_path = Path(settings.ark_serverfiles_base)
    user_serverfiles_path = base_path / f"user_{user_id}"
    return user_serverfiles_path

def get_server_path(server_id: Optional[int], cluster_id: Optional[str] = None) -> Path:
    """
    Szerver útvonal generálása (cluster serverfiles mappában)
    
    Args:
        server_id: Szerver ID
        cluster_id: Cluster ID (kötelező)
    
    Returns:
        Path objektum a szerver útvonalához
    """
    if not cluster_id:
        raise ValueError("cluster_id kötelező az Ark szerverekhez")
    
    # Cluster serverfiles mappa
    cluster_serverfiles = get_cluster_serverfiles_path(cluster_id)
    server_path = cluster_serverfiles / f"server_{server_id}"
    
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
        
        # Felhasználó serverfiles mappa létrehozása
        user_serverfiles = get_user_serverfiles_path(server_instance.server_admin_id)
        user_serverfiles.mkdir(parents=True, exist_ok=True)
        
        # Szerver útvonal a felhasználó serverfiles mappában
        server_path = user_serverfiles / f"server_{server_id}"
        
        # Szülő könyvtárak létrehozása
        server_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Ha már létezik, töröljük
        if server_path.exists() or server_path.is_symlink():
            if server_path.is_symlink():
                server_path.unlink()
            else:
                shutil.rmtree(server_path)
        
        # Symlink létrehozása az aktív Ark fájlokhoz
        server_path.symlink_to(install_path)
        
        # Alapértelmezett konfigurációs fájlok másolása
        copy_default_config_files(server_path)
        
        return server_path
    finally:
        if should_close:
            db.close()

def remove_server_symlink(server_id: int, cluster_id: Optional[str] = None) -> bool:
    """
    Symlink törlése
    
    Args:
        server_id: Szerver ID
        cluster_id: Cluster ID (opcionális)
    
    Returns:
        True ha sikeres, False egyébként
    """
    try:
        server_path = get_server_path(server_id, cluster_id)
        
        if server_path.exists() or server_path.is_symlink():
            if server_path.is_symlink():
                server_path.unlink()
            else:
                shutil.rmtree(server_path)
            return True
        
        return False
    except Exception:
        return False

def get_server_config_path(server_path: Path) -> Path:
    """Szerver konfigurációs fájl útvonala"""
    return server_path / "ShooterGame" / "Saved" / "Config" / "WindowsServer"

def get_default_config_path() -> Path:
    """Alapértelmezett konfigurációs fájlok útvonala"""
    return Path("/home/ai_developer/ZedinSteamManager/Server/ArkAscended/defaults")

def copy_default_config_files(server_path: Path) -> bool:
    """
    Alapértelmezett konfigurációs fájlok másolása a szerverhez
    
    Args:
        server_path: Szerver útvonal (symlink)
    
    Returns:
        True ha sikeres, False egyébként
    """
    try:
        default_config_path = get_default_config_path()
        
        # Ellenőrizzük, hogy létezik-e a defaults mappa
        if not default_config_path.exists():
            print(f"Figyelmeztetés: Alapértelmezett config mappa nem található: {default_config_path}")
            return False
        
        # Szerver config mappa útvonala
        server_config_path = get_server_config_path(server_path)
        
        # Ha a server_path symlink, akkor a config mappa is a symlink mögött lesz
        # De mivel symlink-et használunk, a config fájlokat közvetlenül a symlink mögé kell másolni
        # A symlink mögötti tényleges útvonal
        if server_path.is_symlink():
            real_server_path = server_path.resolve()
        else:
            real_server_path = server_path
        
        real_config_path = real_server_path / "ShooterGame" / "Saved" / "Config" / "WindowsServer"
        
        # Config mappa létrehozása, ha nem létezik
        real_config_path.mkdir(parents=True, exist_ok=True)
        
        # Alapértelmezett fájlok másolása
        if default_config_path.is_dir():
            # Rekurzív másolás a defaults mappából
            for item in default_config_path.iterdir():
                dest_item = real_config_path / item.name
                
                if item.is_dir():
                    # Mappa másolása
                    if dest_item.exists():
                        shutil.rmtree(dest_item)
                    shutil.copytree(item, dest_item)
                else:
                    # Fájl másolása
                    shutil.copy2(item, dest_item)
            
            print(f"Alapértelmezett config fájlok másolva: {default_config_path} -> {real_config_path}")
            return True
        else:
            print(f"Figyelmeztetés: Alapértelmezett config útvonal nem mappa: {default_config_path}")
            return False
            
    except Exception as e:
        print(f"Hiba az alapértelmezett config fájlok másolásakor: {e}")
        import traceback
        traceback.print_exc()
        return False


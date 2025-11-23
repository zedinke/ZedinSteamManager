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


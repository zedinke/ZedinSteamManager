"""
Symlink kezelő szolgáltatás - szerverfájlok symlink kezelése
"""

import os
import shutil
from pathlib import Path
from typing import Optional
from sqlalchemy.orm import Session
from app.config import settings
from app.database import ArkServerFiles, SessionLocal

def get_cluster_serverfiles_path(cluster_id: str) -> Path:
    """
    Cluster serverfiles mappa útvonala
    
    Args:
        cluster_id: Cluster ID
    
    Returns:
        Path objektum a cluster serverfiles mappájához
    """
    base_path = Path(settings.ark_serverfiles_base)
    cluster_serverfiles_path = base_path / cluster_id
    return cluster_serverfiles_path

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

def get_active_cluster_serverfiles(db: Session, cluster_id: int) -> Optional[Path]:
    """
    Aktív cluster szerverfájlok útvonala
    
    Args:
        db: Adatbázis session
        cluster_id: Cluster ID
    
    Returns:
        Path objektum az aktív szerverfájlok útvonalához vagy None
    """
    from app.database import ClusterServerFiles
    serverfiles = db.query(ClusterServerFiles).filter(
        and_(
            ClusterServerFiles.cluster_id == cluster_id,
            ClusterServerFiles.is_active == True,
            ClusterServerFiles.installation_status == "completed"
        )
    ).first()
    
    if serverfiles:
        install_path = Path(serverfiles.install_path)
        if install_path.exists():
            return install_path
    
    return None

def create_server_symlink(server_id: Optional[int], cluster_id: Optional[str] = None, db: Session = None) -> Optional[Path]:
    """
    Symlink létrehozása a szerverhez (cluster serverfiles mappában)
    
    Args:
        server_id: Szerver ID
        cluster_id: Cluster ID (kötelező)
        db: Adatbázis session
    
    Returns:
        Path objektum a symlink útvonalához vagy None
    """
    if not cluster_id:
        raise ValueError("cluster_id kötelező az Ark szerverekhez")
    
    if db is None:
        db = SessionLocal()
        should_close = True
    else:
        should_close = False
    
    try:
        # Aktív cluster szerverfájlok lekérése
        install_path = get_active_cluster_serverfiles(db, cluster_id)
        if not install_path:
            # Fallback: Manager Admin szerverfájlok
            ark_files = get_active_ark_files(db)
            if not ark_files:
                return None
            install_path = Path(ark_files.install_path)
            if not install_path.exists():
                return None
        
        # Szerver útvonal (cluster serverfiles mappában)
        if server_id is None:
            return None
        
        # Cluster serverfiles mappa létrehozása
        cluster_serverfiles = get_cluster_serverfiles_path(cluster_id)
        cluster_serverfiles.mkdir(parents=True, exist_ok=True)
        
        server_path = get_server_path(server_id, cluster_id)
        
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


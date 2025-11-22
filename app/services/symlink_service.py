"""
Symlink kezelő szolgáltatás - szerverfájlok symlink kezelése
"""

import os
import shutil
from pathlib import Path
from typing import Optional
from app.config import settings
from app.database import ArkServerFiles, Session

def get_server_path(server_id: Optional[int], cluster_id: Optional[str] = None) -> Path:
    """
    Szerver útvonal generálása
    
    Args:
        server_id: Szerver ID
        cluster_id: Cluster ID (opcionális)
    
    Returns:
        Path objektum a szerver útvonalához
    """
    base_path = Path(settings.ark_base_path)
    
    if cluster_id:
        # Ha van cluster, akkor cluster/szerver struktúra
        server_path = base_path / "clusters" / cluster_id / f"server_{server_id}"
    else:
        # Egyébként csak szerver
        server_path = base_path / "servers" / f"server_{server_id}"
    
    return server_path

def get_active_ark_files(db: Session) -> Optional[ArkServerFiles]:
    """Aktív Ark szerverfájlok lekérése"""
    return db.query(ArkServerFiles).filter(
        ArkServerFiles.is_active == True
    ).first()

def create_server_symlink(server_id: Optional[int], cluster_id: Optional[str] = None, db: Session = None) -> Optional[Path]:
    """
    Symlink létrehozása a szerverhez
    
    Args:
        server_id: Szerver ID
        cluster_id: Cluster ID (opcionális)
        db: Adatbázis session
    
    Returns:
        Path objektum a symlink útvonalához vagy None
    """
    if db is None:
        from app.database import SessionLocal
        db = SessionLocal()
        should_close = True
    else:
        should_close = False
    
    try:
        # Aktív Ark fájlok lekérése
        ark_files = get_active_ark_files(db)
        if not ark_files:
            return None
        
        install_path = Path(ark_files.install_path)
        if not install_path.exists():
            return None
        
        # Szerver útvonal
        if server_id is None:
            return None
        
        server_path = get_server_path(server_id, cluster_id)
        
        # Szülő könyvtárak létrehozása
        server_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Ha már létezik, töröljük
        if server_path.exists() or server_path.is_symlink():
            if server_path.is_symlink():
                server_path.unlink()
            else:
                shutil.rmtree(server_path)
        
        # Symlink létrehozása
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


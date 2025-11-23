"""
Backup szolgáltatás - Ark szerver Saved mappa backup kezelése
"""

import os
import shutil
import tarfile
import zipfile
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime
from sqlalchemy.orm import Session
from app.services.symlink_service import get_server_saved_path, get_server_dedicated_saved_path
from app.config import settings

def get_server_backup_path(server_path: Path) -> Path:
    """
    Szerver backup mappa útvonala (Saved mappán kívül)
    
    Args:
        server_path: Szerver útvonal (symlink)
    
    Returns:
        Path objektum a backup mappához
    """
    # Backup mappa a szerver mappájában, de Saved mappán kívül
    # Példa: user_1/server_5 -> user_1/server_5_backups
    backup_path = server_path.parent / f"{server_path.name}_backups"
    return backup_path

def create_backup(server_path: Path, backup_name: Optional[str] = None) -> Optional[Path]:
    """
    Backup készítése a Saved mappa teljes tartalmából
    
    Args:
        server_path: Szerver útvonal (symlink)
        backup_name: Backup fájl neve (opcionális, ha nincs megadva, akkor automatikus)
    
    Returns:
        Path objektum a backup fájlhoz vagy None
    """
    try:
        # Saved mappa útvonala
        saved_path = get_server_saved_path(server_path)
        
        if not saved_path.exists():
            print(f"Saved mappa nem található: {saved_path}")
            return None
        
        # Backup mappa létrehozása
        backup_dir = get_server_backup_path(server_path)
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Backup fájl neve
        if not backup_name:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"backup_{timestamp}.tar.gz"
        
        backup_file = backup_dir / backup_name
        
        # Tar.gz fájl létrehozása
        with tarfile.open(backup_file, "w:gz") as tar:
            # Saved mappa teljes tartalmának hozzáadása
            tar.add(saved_path, arcname="Saved")
        
        print(f"Backup létrehozva: {backup_file}")
        
        # Backup korlátok betartatása
        enforce_backup_limits(server_path)
        
        return backup_file
    except Exception as e:
        print(f"Hiba a backup készítésekor: {e}")
        import traceback
        traceback.print_exc()
        return None

def list_backups(server_path: Path) -> List[Dict]:
    """
    Backup fájlok listázása
    
    Args:
        server_path: Szerver útvonal (symlink)
    
    Returns:
        Lista backup információkról (név, dátum, méret)
    """
    try:
        backup_dir = get_server_backup_path(server_path)
        
        if not backup_dir.exists():
            return []
        
        backups = []
        allowed_extensions = ['.tar.gz', '.tar', '.zip']
        for backup_file in backup_dir.iterdir():
            if backup_file.is_file():
                # Ellenőrizzük, hogy a fájl neve valamelyik engedélyezett kiterjesztéssel végződik-e
                file_name_lower = backup_file.name.lower()
                is_valid_backup = any(file_name_lower.endswith(ext) for ext in allowed_extensions)
                
                if is_valid_backup:
                    stat = backup_file.stat()
                    backups.append({
                        "name": backup_file.name,
                        "path": str(backup_file),
                        "size": stat.st_size,
                        "created": datetime.fromtimestamp(stat.st_mtime),
                        "size_mb": round(stat.st_size / (1024 * 1024), 2)
                    })
        
        # Dátum szerint rendezés (legújabb először)
        backups.sort(key=lambda x: x["created"], reverse=True)
        
        return backups
    except Exception as e:
        print(f"Hiba a backup listázásakor: {e}")
        import traceback
        traceback.print_exc()
        return []

def restore_backup(server_path: Path, backup_name: str) -> bool:
    """
    Backup visszaállítása
    
    Args:
        server_path: Szerver útvonal (symlink)
        backup_name: Backup fájl neve
    
    Returns:
        True ha sikeres, False egyébként
    """
    try:
        # Backup mappa és fájl
        backup_dir = get_server_backup_path(server_path)
        backup_file = backup_dir / backup_name
        
        if not backup_file.exists():
            print(f"Backup fájl nem található: {backup_file}")
            return False
        
        # Saved mappa útvonala
        saved_path = get_server_saved_path(server_path)
        
        # Ha a Saved mappa létezik, biztonsági másolat készítése
        if saved_path.exists():
            # Biztonsági másolat neve
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safety_backup = backup_dir / f"safety_backup_before_restore_{timestamp}.tar.gz"
            
            # Biztonsági másolat készítése
            with tarfile.open(safety_backup, "w:gz") as tar:
                tar.add(saved_path, arcname="Saved")
            
            print(f"Biztonsági másolat készítve: {safety_backup}")
        
        # Saved mappa tartalmának törlése (de a mappa marad)
        if saved_path.exists():
            for item in saved_path.iterdir():
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
        
        # Backup kicsomagolása
        if backup_file.suffix == '.tar.gz' or backup_file.suffix == '.tar':
            with tarfile.open(backup_file, "r:*") as tar:
                # Kicsomagolás ideiglenes mappába
                temp_extract = saved_path.parent / "temp_backup_extract"
                tar.extractall(temp_extract)
                
                # Ha a backup "Saved" mappát tartalmazza, akkor azt másoljuk
                extracted_saved = temp_extract / "Saved"
                if extracted_saved.exists():
                    # Saved mappa tartalmának másolása
                    for item in extracted_saved.iterdir():
                        dest_item = saved_path / item.name
                        if item.is_dir():
                            if dest_item.exists():
                                shutil.rmtree(dest_item)
                            shutil.copytree(item, dest_item)
                        else:
                            shutil.copy2(item, dest_item)
                    
                    # Ideiglenes mappa törlése
                    shutil.rmtree(temp_extract)
                else:
                    # Ha nincs "Saved" mappa, akkor a teljes tartalmat másoljuk
                    for item in temp_extract.iterdir():
                        dest_item = saved_path / item.name
                        if item.is_dir():
                            if dest_item.exists():
                                shutil.rmtree(dest_item)
                            shutil.copytree(item, dest_item)
                        else:
                            shutil.copy2(item, dest_item)
                    
                    # Ideiglenes mappa törlése
                    shutil.rmtree(temp_extract)
        elif backup_file.suffix == '.zip':
            with zipfile.ZipFile(backup_file, 'r') as zip_ref:
                # Kicsomagolás ideiglenes mappába
                temp_extract = saved_path.parent / "temp_backup_extract"
                zip_ref.extractall(temp_extract)
                
                # Ha a backup "Saved" mappát tartalmazza, akkor azt másoljuk
                extracted_saved = temp_extract / "Saved"
                if extracted_saved.exists():
                    # Saved mappa tartalmának másolása
                    for item in extracted_saved.iterdir():
                        dest_item = saved_path / item.name
                        if item.is_dir():
                            if dest_item.exists():
                                shutil.rmtree(dest_item)
                            shutil.copytree(item, dest_item)
                        else:
                            shutil.copy2(item, dest_item)
                    
                    # Ideiglenes mappa törlése
                    shutil.rmtree(temp_extract)
                else:
                    # Ha nincs "Saved" mappa, akkor a teljes tartalmat másoljuk
                    for item in temp_extract.iterdir():
                        dest_item = saved_path / item.name
                        if item.is_dir():
                            if dest_item.exists():
                                shutil.rmtree(dest_item)
                            shutil.copytree(item, dest_item)
                        else:
                            shutil.copy2(item, dest_item)
                    
                    # Ideiglenes mappa törlése
                    shutil.rmtree(temp_extract)
        else:
            print(f"Nem támogatott backup formátum: {backup_file.suffix}")
            return False
        
        print(f"Backup visszaállítva: {backup_file}")
        return True
    except Exception as e:
        print(f"Hiba a backup visszaállításakor: {e}")
        import traceback
        traceback.print_exc()
        return False

def delete_backup(server_path: Path, backup_name: str) -> bool:
    """
    Backup fájl törlése
    
    Args:
        server_path: Szerver útvonal (symlink)
        backup_name: Backup fájl neve
    
    Returns:
        True ha sikeres, False egyébként
    """
    try:
        backup_dir = get_server_backup_path(server_path)
        backup_file = backup_dir / backup_name
        
        if not backup_file.exists():
            print(f"Backup fájl nem található: {backup_file}")
            return False
        
        backup_file.unlink()
        print(f"Backup törölve: {backup_file}")
        return True
    except Exception as e:
        print(f"Hiba a backup törlésekor: {e}")
        import traceback
        traceback.print_exc()
        return False

def get_total_backup_size() -> int:
    """
    Összes backup fájl teljes méretének számítása (bájtokban)
    
    Returns:
        Összes backup méret bájtokban
    """
    try:
        from app.database import ServerInstance, SessionLocal
        from app.database import Cluster
        
        db = SessionLocal()
        total_size = 0
        
        try:
            # Összes szerver lekérése
            servers = db.query(ServerInstance).all()
            
            for server in servers:
                # Szerver útvonal meghatározása
                if server.server_path:
                    server_path = Path(server.server_path)
                else:
                    cluster = db.query(Cluster).filter(Cluster.id == server.cluster_id).first()
                    if not cluster:
                        continue
                    from app.services.symlink_service import get_server_path
                    server_path = get_server_path(server.id, cluster.cluster_id, server.server_admin_id)
                
                if not server_path or not server_path.exists():
                    continue
                
                # Backup mappa
                backup_dir = get_server_backup_path(server_path)
                if not backup_dir.exists():
                    continue
                
                # Backup fájlok méretének összegzése
                allowed_extensions = ['.tar.gz', '.tar', '.zip']
                for backup_file in backup_dir.iterdir():
                    if backup_file.is_file():
                        file_name_lower = backup_file.name.lower()
                        is_valid_backup = any(file_name_lower.endswith(ext) for ext in allowed_extensions)
                        
                        if is_valid_backup:
                            total_size += backup_file.stat().st_size
        finally:
            db.close()
        
        return total_size
    except Exception as e:
        print(f"Hiba az összes backup méretének számításakor: {e}")
        import traceback
        traceback.print_exc()
        return 0

def delete_oldest_backup(server_path: Optional[Path] = None) -> bool:
    """
    Legrégebbi backup törlése
    
    Args:
        server_path: Ha megadva, csak ezen a szerveren belül keresi a legrégebbit,
                     ha None, akkor az összes szerver között keresi a legrégebbit
    
    Returns:
        True ha sikeres, False egyébként
    """
    try:
        from app.database import ServerInstance, SessionLocal
        from app.database import Cluster
        
        db = SessionLocal()
        oldest_backup = None
        oldest_date = None
        
        try:
            if server_path:
                # Csak egy szerver backup-jai között keresünk
                backup_dir = get_server_backup_path(server_path)
                if backup_dir.exists():
                    allowed_extensions = ['.tar.gz', '.tar', '.zip']
                    for backup_file in backup_dir.iterdir():
                        if backup_file.is_file():
                            file_name_lower = backup_file.name.lower()
                            is_valid_backup = any(file_name_lower.endswith(ext) for ext in allowed_extensions)
                            
                            if is_valid_backup:
                                backup_date = datetime.fromtimestamp(backup_file.stat().st_mtime)
                                if oldest_date is None or backup_date < oldest_date:
                                    oldest_date = backup_date
                                    oldest_backup = backup_file
            else:
                # Összes szerver backup-jai között keresünk
                servers = db.query(ServerInstance).all()
                
                for server in servers:
                    # Szerver útvonal meghatározása
                    if server.server_path:
                        current_server_path = Path(server.server_path)
                    else:
                        cluster = db.query(Cluster).filter(Cluster.id == server.cluster_id).first()
                        if not cluster:
                            continue
                        from app.services.symlink_service import get_server_path
                        current_server_path = get_server_path(server.id, cluster.cluster_id, server.server_admin_id)
                    
                    if not current_server_path or not current_server_path.exists():
                        continue
                    
                    # Backup mappa
                    backup_dir = get_server_backup_path(current_server_path)
                    if not backup_dir.exists():
                        continue
                    
                    # Backup fájlok keresése
                    allowed_extensions = ['.tar.gz', '.tar', '.zip']
                    for backup_file in backup_dir.iterdir():
                        if backup_file.is_file():
                            file_name_lower = backup_file.name.lower()
                            is_valid_backup = any(file_name_lower.endswith(ext) for ext in allowed_extensions)
                            
                            if is_valid_backup:
                                backup_date = datetime.fromtimestamp(backup_file.stat().st_mtime)
                                if oldest_date is None or backup_date < oldest_date:
                                    oldest_date = backup_date
                                    oldest_backup = backup_file
        finally:
            db.close()
        
        # Legrégebbi backup törlése
        if oldest_backup and oldest_backup.exists():
            oldest_backup.unlink()
            print(f"Legrégebbi backup törölve: {oldest_backup}")
            return True
        
        return False
    except Exception as e:
        print(f"Hiba a legrégebbi backup törlésekor: {e}")
        import traceback
        traceback.print_exc()
        return False

def enforce_backup_limits(server_path: Path) -> None:
    """
    Backup korlátok betartatása - törli a legrégebbi backup-okat, ha szükséges
    
    Args:
        server_path: Szerver útvonal
    """
    try:
        # 1. Ellenőrizzük a szerver-specifikus korlátot (max 20 db)
        backups = list_backups(server_path)
        max_per_server = settings.backup_max_per_server
        
        # Töröljük a legrégebbieket, amíg a korlát alatt vagyunk
        while len(backups) >= max_per_server:
            # Legrégebbi backup keresése ezen a szerveren
            if backups:
                # Rendezzük dátum szerint (legrégebbi először)
                backups_sorted = sorted(backups, key=lambda x: x["created"])
                oldest = backups_sorted[0]
                
                # Törlés
                if delete_backup(server_path, oldest["name"]):
                    backups.remove(oldest)
                    print(f"Backup törölve korlát miatt (szerver-specifikus): {oldest['name']}")
                else:
                    break
            else:
                break
        
        # 2. Ellenőrizzük az összes backup méretét (max 20GB)
        max_total_size_bytes = settings.backup_max_total_size_gb * 1024 * 1024 * 1024
        total_size = get_total_backup_size()
        
        # Töröljük a legrégebbieket, amíg a korlát alatt vagyunk
        while total_size >= max_total_size_bytes:
            # Legrégebbi backup keresése (összes szerver között)
            if delete_oldest_backup():
                # Újraszámoljuk a méretet
                total_size = get_total_backup_size()
                print(f"Backup törölve korlát miatt (összes méret): {total_size / (1024*1024*1024):.2f} GB")
            else:
                # Ha nem sikerült törölni, kilépünk
                break
                
    except Exception as e:
        print(f"Hiba a backup korlátok betartatásakor: {e}")
        import traceback
        traceback.print_exc()

def upload_backup(server_path: Path, uploaded_file, filename: str) -> Optional[Path]:
    """
    Backup fájl feltöltése
    
    Args:
        server_path: Szerver útvonal (symlink)
        uploaded_file: Feltöltött fájl objektum
        filename: Fájl neve
    
    Returns:
        Path objektum a feltöltött backup fájlhoz vagy None
    """
    try:
        # Backup mappa létrehozása
        backup_dir = get_server_backup_path(server_path)
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Fájl mentése
        backup_file = backup_dir / filename
        
        # Fájl írása
        with open(backup_file, "wb") as f:
            # Feltöltött fájl tartalmának másolása
            shutil.copyfileobj(uploaded_file, f)
        
        print(f"Backup feltöltve: {backup_file}")
        
        # Backup korlátok betartatása
        enforce_backup_limits(server_path)
        
        return backup_file
    except Exception as e:
        print(f"Hiba a backup feltöltésekor: {e}")
        import traceback
        traceback.print_exc()
        return None


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
        return backup_file
    except Exception as e:
        print(f"Hiba a backup feltöltésekor: {e}")
        import traceback
        traceback.print_exc()
        return None


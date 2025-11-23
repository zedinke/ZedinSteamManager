#!/usr/bin/env python3
"""
Automatikus repo frissítő cron job
Ez a script rendszeresen ellenőrzi és frissíti a repository-t
"""

import sys
import subprocess
from pathlib import Path
import logging

# Projekt gyökér hozzáadása a path-hoz
BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

# Logs könyvtár létrehozása, ha nem létezik
logs_dir = BASE_DIR / "logs"
logs_dir.mkdir(exist_ok=True)

# Logging beállítása
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(logs_dir / 'auto_update.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def get_current_branch(project_dir: Path) -> str:
    """Visszaadja a jelenlegi git branch nevét"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return "main"  # Alapértelmezett
    except:
        return "main"  # Alapértelmezett

def check_for_updates(project_dir: Path) -> bool:
    """Ellenőrzi, hogy van-e új commit a remote repository-ban"""
    try:
        # Jelenlegi branch meghatározása
        current_branch = get_current_branch(project_dir)
        logger.info(f"Jelenlegi branch: {current_branch}")
        
        # Git fetch
        result = subprocess.run(
            ["git", "fetch", "origin", current_branch],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            logger.warning(f"Git fetch sikertelen: {result.stderr}")
            return False
        
        # Git log ellenőrzése - van-e új commit?
        result = subprocess.run(
            ["git", "log", f"HEAD..origin/{current_branch}", "--oneline"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        has_update = len(result.stdout.strip()) > 0
        
        if has_update:
            commits = result.stdout.strip().split("\n")[:5]  # Legutóbbi 5 commit
            logger.info(f"Új frissítések találhatók ({len(commits)} commit):")
            for commit in commits:
                logger.info(f"  - {commit}")
        
        return has_update
    except subprocess.TimeoutExpired:
        logger.error("Git művelet túllépte az időkorlátot")
        return False
    except Exception as e:
        logger.error(f"Hiba történt az update ellenőrzésekor: {e}")
        return False

def is_update_in_progress(project_dir: Path) -> bool:
    """Ellenőrzi, hogy már folyamatban van-e egy update"""
    flag_file = project_dir / ".updating"
    return flag_file.exists()

def execute_update(project_dir: Path) -> bool:
    """Végrehajtja az update scriptet"""
    update_script = project_dir / "scripts" / "update.sh"
    
    if not update_script.exists():
        logger.error(f"Update script nem található: {update_script}")
        return False
    
    # Ellenőrizzük, hogy már folyamatban van-e update
    if is_update_in_progress(project_dir):
        logger.warning("Update már folyamatban van, kihagyva...")
        return False
    
    try:
        logger.info("Update script futtatása...")
        # Update script futtatása
        result = subprocess.run(
            ["bash", str(update_script)],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=600  # 10 perc timeout
        )
        
        if result.returncode == 0:
            logger.info("✅ Update sikeresen befejezve!")
            if result.stdout:
                logger.info(f"Update kimenet:\n{result.stdout}")
            return True
        else:
            logger.error(f"❌ Update sikertelen (exit code: {result.returncode})")
            if result.stderr:
                logger.error(f"Hibaüzenet:\n{result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        logger.error("Update script túllépte az időkorlátot (10 perc)")
        return False
    except Exception as e:
        logger.error(f"Hiba történt az update futtatása során: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def main():
    """Fő függvény"""
    project_dir = BASE_DIR
    
    # Ellenőrizzük, hogy git repository-e
    if not (project_dir / ".git").exists():
        logger.error(f"A projekt könyvtár nem git repository: {project_dir}")
        sys.exit(1)
    
    logger.info("=" * 60)
    logger.info("Automatikus repo frissítés ellenőrzése...")
    logger.info(f"Projekt könyvtár: {project_dir}")
    
    # Ellenőrizzük, hogy van-e update folyamatban
    if is_update_in_progress(project_dir):
        logger.warning("Update már folyamatban van, kihagyva...")
        sys.exit(0)
    
    # Ellenőrizzük, hogy van-e új commit
    has_update = check_for_updates(project_dir)
    
    if not has_update:
        logger.info("Nincs új frissítés.")
        sys.exit(0)
    
    # Ha van update, futtatjuk az update scriptet
    logger.info("Új frissítések találhatók, update indítása...")
    success = execute_update(project_dir)
    
    if success:
        logger.info("Automatikus frissítés sikeresen befejezve!")
        sys.exit(0)
    else:
        logger.error("Automatikus frissítés sikertelen!")
        sys.exit(1)

if __name__ == "__main__":
    main()


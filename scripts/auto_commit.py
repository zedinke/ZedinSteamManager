#!/usr/bin/env python3
"""
Automatikus git commit és push script
Ez a script automatikusan commitol és pushol minden módosítást
"""

import sys
import subprocess
from pathlib import Path
import logging
from datetime import datetime

# Projekt gyökér
BASE_DIR = Path(__file__).parent.parent

# Logging beállítása
logs_dir = BASE_DIR / "logs"
logs_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(logs_dir / 'auto_commit.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def get_git_status(project_dir: Path) -> dict:
    """Visszaadja a git státuszt"""
    try:
        # Módosított fájlok
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            return {"has_changes": False, "files": []}
        
        lines = result.stdout.strip().split("\n")
        files = [line.strip() for line in lines if line.strip()]
        
        return {
            "has_changes": len(files) > 0,
            "files": files
        }
    except Exception as e:
        logger.error(f"Hiba a git status ellenőrzésekor: {e}")
        return {"has_changes": False, "files": []}

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

def auto_commit_and_push(project_dir: Path, commit_message: str = None) -> bool:
    """Automatikusan commitol és pushol minden módosítást"""
    try:
        # Ellenőrizzük, hogy git repository-e
        if not (project_dir / ".git").exists():
            logger.error(f"A projekt könyvtár nem git repository: {project_dir}")
            return False
        
        # Git status ellenőrzése
        status = get_git_status(project_dir)
        
        if not status["has_changes"]:
            logger.info("Nincs módosítás a commitoláshoz.")
            return True
        
        logger.info(f"Módosított fájlok ({len(status['files'])}):")
        for file in status["files"][:10]:  # Legfeljebb 10 fájl
            logger.info(f"  - {file}")
        if len(status["files"]) > 10:
            logger.info(f"  ... és még {len(status['files']) - 10} fájl")
        
        # Összes módosítás hozzáadása
        logger.info("Fájlok hozzáadása (git add)...")
        result = subprocess.run(
            ["git", "add", "-A"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            logger.error(f"Git add sikertelen: {result.stderr}")
            return False
        
        # Commit message generálása, ha nincs megadva
        if not commit_message:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            commit_message = f"Auto-commit: {timestamp}\n\nMódosított fájlok: {len(status['files'])}"
        
        # Commit
        logger.info("Commit létrehozása...")
        result = subprocess.run(
            ["git", "commit", "-m", commit_message],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            if "nothing to commit" in result.stdout.lower() or "nothing to commit" in result.stderr.lower():
                logger.info("Nincs új módosítás a commitoláshoz.")
                return True
            logger.error(f"Git commit sikertelen: {result.stderr}")
            return False
        
        logger.info(f"✅ Commit sikeres: {result.stdout.strip()}")
        
        # Branch meghatározása
        current_branch = get_current_branch(project_dir)
        logger.info(f"Jelenlegi branch: {current_branch}")
        
        # Push
        logger.info("Push futtatása...")
        result = subprocess.run(
            ["git", "push", "origin", current_branch],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode != 0:
            logger.error(f"Git push sikertelen: {result.stderr}")
            # Lehet, hogy nincs upstream branch, próbáljuk meg set-upstream-mel
            logger.info("Upstream branch beállítása...")
            result = subprocess.run(
                ["git", "push", "--set-upstream", "origin", current_branch],
                cwd=project_dir,
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.returncode != 0:
                logger.error(f"Git push (set-upstream) sikertelen: {result.stderr}")
                return False
        
        logger.info(f"✅ Push sikeres!")
        return True
        
    except subprocess.TimeoutExpired:
        logger.error("Git művelet túllépte az időkorlátot")
        return False
    except Exception as e:
        logger.error(f"Hiba történt: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def main():
    """Fő függvény"""
    project_dir = BASE_DIR
    
    # Commit message opcionális argumentumként
    commit_message = None
    if len(sys.argv) > 1:
        commit_message = " ".join(sys.argv[1:])
    
    logger.info("=" * 60)
    logger.info("Automatikus git commit és push...")
    logger.info(f"Projekt könyvtár: {project_dir}")
    
    success = auto_commit_and_push(project_dir, commit_message)
    
    if success:
        logger.info("✅ Automatikus commit és push sikeres!")
        sys.exit(0)
    else:
        logger.error("❌ Automatikus commit és push sikertelen!")
        sys.exit(1)

if __name__ == "__main__":
    main()


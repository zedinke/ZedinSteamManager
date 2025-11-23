"""
Cron job beállítása automatikus backup-hoz
Ez a script beállítja a cron job-okat minden szerverhez, ahol automatikus backup van beállítva
"""

import sys
import os
from pathlib import Path
import subprocess

# Projekt gyökér
project_root = Path(__file__).parent.parent
cron_script = project_root / "cron" / "auto_backup.py"
python_path = sys.executable

def setup_cron_jobs():
    """
    Cron job-ok beállítása automatikus backup-hoz
    """
    # Cron job parancsok
    cron_commands = [
        # 3 óránként
        f"0 */3 * * * cd {project_root} && {python_path} {cron_script} >> {project_root}/logs/auto_backup.log 2>&1",
        # 6 óránként
        f"0 */6 * * * cd {project_root} && {python_path} {cron_script} >> {project_root}/logs/auto_backup.log 2>&1",
        # 12 óránként
        f"0 */12 * * * cd {project_root} && {python_path} {cron_script} >> {project_root}/logs/auto_backup.log 2>&1",
        # 24 óránként (naponta egyszer)
        f"0 0 * * * cd {project_root} && {python_path} {cron_script} >> {project_root}/logs/auto_backup.log 2>&1"
    ]
    
    # Logs mappa létrehozása
    logs_dir = project_root / "logs"
    logs_dir.mkdir(exist_ok=True)
    
    # Cron job-ok hozzáadása (ha még nincsenek benne)
    try:
        # Jelenlegi cron job-ok lekérése
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        current_crontab = result.stdout if result.returncode == 0 else ""
        
        # Új cron job-ok hozzáadása (ha még nincsenek benne)
        new_crontab = current_crontab
        for cmd in cron_commands:
            if cmd not in current_crontab:
                new_crontab += cmd + "\n"
        
        # Cron job-ok frissítése
        if new_crontab != current_crontab:
            process = subprocess.Popen(["crontab", "-"], stdin=subprocess.PIPE, text=True)
            process.communicate(input=new_crontab)
            print("Cron job-ok beállítva automatikus backup-hoz")
        else:
            print("Cron job-ok már be vannak állítva")
            
    except Exception as e:
        print(f"Hiba a cron job beállításakor: {e}")
        print("Manuálisan állítsd be a cron job-okat:")
        for cmd in cron_commands:
            print(f"  {cmd}")

if __name__ == "__main__":
    setup_cron_jobs()


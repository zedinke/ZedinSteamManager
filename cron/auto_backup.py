"""
Automatikus backup készítés Ark szerverekhez
Cron job: futtatandó az automatikus backup intervallumok szerint
"""

import sys
import os
from pathlib import Path

# Projekt gyökér hozzáadása a Python path-hoz
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.orm import Session
from app.database import SessionLocal, ServerInstance
from app.services.backup_service import create_backup
from app.services.symlink_service import get_server_path
from pathlib import Path as PathLib
from datetime import datetime

def run_auto_backup():
    """
    Automatikus backup készítése minden szerverhez, ahol be van állítva
    """
    db: Session = SessionLocal()
    
    try:
        # Összes Ark szerver lekérése
        servers = db.query(ServerInstance).all()
        
        backup_count = 0
        error_count = 0
        
        for server in servers:
            try:
                # Config ellenőrzése
                server_config = server.config if server.config else {}
                auto_backup_interval = server_config.get("AUTO_BACKUP_INTERVAL")
                
                if not auto_backup_interval:
                    # Nincs automatikus backup beállítva
                    continue
                
                # Szerver útvonal
                if server.server_path:
                    server_path = PathLib(server.server_path)
                else:
                    from app.database import Cluster
                    cluster = db.query(Cluster).filter(Cluster.id == server.cluster_id).first()
                    if not cluster:
                        continue
                    server_path = get_server_path(server.id, cluster.cluster_id, server.server_admin_id)
                
                if not server_path or not server_path.exists():
                    print(f"Szerver {server.id} útvonal nem található: {server_path}")
                    continue
                
                # Backup készítése
                backup_file = create_backup(server_path)
                
                if backup_file:
                    backup_count += 1
                    print(f"Backup készítve: Szerver {server.id} ({server.name}) -> {backup_file}")
                else:
                    error_count += 1
                    print(f"Backup sikertelen: Szerver {server.id} ({server.name})")
                    
            except Exception as e:
                error_count += 1
                print(f"Hiba a szerver {server.id} backup készítésekor: {e}")
                import traceback
                traceback.print_exc()
        
        print(f"Automatikus backup befejezve: {backup_count} sikeres, {error_count} hiba")
        
    except Exception as e:
        print(f"Hiba az automatikus backup futtatásakor: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    run_auto_backup()


"""
Ark szerver backup kezelő router
"""

from fastapi import APIRouter, Request, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from sqlalchemy.orm import Session
from pathlib import Path
from app.database import get_db, ServerInstance
from app.services.backup_service import (
    create_backup, list_backups, restore_backup, delete_backup, upload_backup,
    get_server_backup_path
)
from app.services.symlink_service import get_server_path
from sqlalchemy import and_

# require_server_admin import az ark_servers.py-ból
def require_server_admin(request: Request, db: Session = Depends(get_db)):
    """Server Admin jogosultság ellenőrzése"""
    from app.database import User
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=302,
            detail="Nincs bejelentkezve",
            headers={"Location": "/login"}
        )
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=302,
            detail="Felhasználó nem található",
            headers={"Location": "/login"}
        )
    
    if user.role != "server_admin":
        raise HTTPException(
            status_code=403,
            detail="Nincs jogosultsága ehhez a művelethez"
        )
    
    return user

router = APIRouter(prefix="/ark/servers", tags=["ark_backup"])

@router.get("/{server_id}/backup", response_class=HTMLResponse)
async def show_backup(
    request: Request,
    server_id: int,
    db: Session = Depends(get_db)
):
    """Backup kezelő oldal"""
    from app.main import templates
    
    current_user = require_server_admin(request, db)
    
    # Szerver lekérése
    server = db.query(ServerInstance).filter(
        and_(
            ServerInstance.id == server_id,
            ServerInstance.server_admin_id == current_user.id
        )
    ).first()
    
    if not server:
        raise HTTPException(status_code=404, detail="Szerver nem található")
    
    # Szerver útvonal
    if server.server_path:
        server_path = Path(server.server_path)
    else:
        from app.database import Cluster
        cluster = db.query(Cluster).filter(Cluster.id == server.cluster_id).first()
        if not cluster:
            raise HTTPException(status_code=404, detail="Cluster nem található")
        server_path = get_server_path(server.id, cluster.cluster_id, server.server_admin_id)
    
    # Backup lista
    backups = list_backups(server_path)
    
    # Backup beállítások a config-ból
    server_config = server.config if server.config else {}
    auto_backup_interval = server_config.get("AUTO_BACKUP_INTERVAL", None)  # 3, 6, 12, 24 óra
    
    # Utolsó backup időpontja (legújabb backup létrehozási ideje)
    last_backup_time = None
    if backups and len(backups) > 0:
        last_backup_time = backups[0]["created"]  # Legújabb backup (rendezve van)
    
    # Következő backup ideje számítása
    next_backup_time = None
    if auto_backup_interval and last_backup_time:
        from datetime import timedelta
        next_backup_time = last_backup_time + timedelta(hours=int(auto_backup_interval))
    elif auto_backup_interval:
        # Ha nincs még backup, akkor az intervallum órával később lesz
        from datetime import datetime, timedelta
        next_backup_time = datetime.now() + timedelta(hours=int(auto_backup_interval))
    
    return templates.TemplateResponse("ark/server_backup.html", {
        "request": request,
        "current_user": current_user,
        "server": server,
        "backups": backups,
        "auto_backup_interval": auto_backup_interval,
        "last_backup_time": last_backup_time,
        "next_backup_time": next_backup_time
    })

@router.post("/{server_id}/backup/create")
async def create_backup_endpoint(
    request: Request,
    server_id: int,
    db: Session = Depends(get_db)
):
    """Backup készítése"""
    current_user = require_server_admin(request, db)
    
    # Szerver lekérése
    server = db.query(ServerInstance).filter(
        and_(
            ServerInstance.id == server_id,
            ServerInstance.server_admin_id == current_user.id
        )
    ).first()
    
    if not server:
        raise HTTPException(status_code=404, detail="Szerver nem található")
    
    # Szerver útvonal
    if server.server_path:
        server_path = Path(server.server_path)
    else:
        from app.database import Cluster
        cluster = db.query(Cluster).filter(Cluster.id == server.cluster_id).first()
        if not cluster:
            raise HTTPException(status_code=404, detail="Cluster nem található")
        server_path = get_server_path(server.id, cluster.cluster_id, server.server_admin_id)
    
    # Backup készítése
    backup_file = create_backup(server_path)
    
    if backup_file:
        return RedirectResponse(
            url=f"/ark/servers/{server_id}/backup?success=Backup+készítve",
            status_code=302
        )
    else:
        return RedirectResponse(
            url=f"/ark/servers/{server_id}/backup?error=Backup+készítése+sikertelen",
            status_code=302
        )

@router.get("/{server_id}/backup/{backup_name}/download")
async def download_backup(
    request: Request,
    server_id: int,
    backup_name: str,
    db: Session = Depends(get_db)
):
    """Backup letöltése"""
    current_user = require_server_admin(request, db)
    
    # Szerver lekérése
    server = db.query(ServerInstance).filter(
        and_(
            ServerInstance.id == server_id,
            ServerInstance.server_admin_id == current_user.id
        )
    ).first()
    
    if not server:
        raise HTTPException(status_code=404, detail="Szerver nem található")
    
    # Szerver útvonal
    if server.server_path:
        server_path = Path(server.server_path)
    else:
        from app.database import Cluster
        cluster = db.query(Cluster).filter(Cluster.id == server.cluster_id).first()
        if not cluster:
            raise HTTPException(status_code=404, detail="Cluster nem található")
        server_path = get_server_path(server.id, cluster.cluster_id, server.server_admin_id)
    
    # Backup fájl
    backup_dir = get_server_backup_path(server_path)
    backup_file = backup_dir / backup_name
    
    if not backup_file.exists():
        raise HTTPException(status_code=404, detail="Backup fájl nem található")
    
    # Media type meghatározása a fájl kiterjesztése alapján
    media_type_map = {
        '.tar.gz': 'application/gzip',
        '.tar': 'application/x-tar',
        '.zip': 'application/zip'
    }
    
    # Fájl kiterjesztés meghatározása
    file_ext = None
    for ext in media_type_map.keys():
        if backup_name.endswith(ext):
            file_ext = ext
            break
    
    media_type = media_type_map.get(file_ext, 'application/octet-stream')
    
    return FileResponse(
        path=str(backup_file),
        filename=backup_name,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{backup_name}"'
        }
    )

@router.post("/{server_id}/backup/upload")
async def upload_backup_endpoint(
    request: Request,
    server_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Backup feltöltése"""
    current_user = require_server_admin(request, db)
    
    # Szerver lekérése
    server = db.query(ServerInstance).filter(
        and_(
            ServerInstance.id == server_id,
            ServerInstance.server_admin_id == current_user.id
        )
    ).first()
    
    if not server:
        raise HTTPException(status_code=404, detail="Szerver nem található")
    
    # Szerver útvonal
    if server.server_path:
        server_path = Path(server.server_path)
    else:
        from app.database import Cluster
        cluster = db.query(Cluster).filter(Cluster.id == server.cluster_id).first()
        if not cluster:
            raise HTTPException(status_code=404, detail="Cluster nem található")
        server_path = get_server_path(server.id, cluster.cluster_id, server.server_admin_id)
    
    # Fájl ellenőrzése
    if not file.filename:
        return RedirectResponse(
            url=f"/ark/servers/{server_id}/backup?error=Nincs+fájl+kiválasztva",
            status_code=302
        )
    
    # Fájl kiterjesztés ellenőrzése
    allowed_extensions = ['.tar.gz', '.tar', '.zip']
    if not any(file.filename.endswith(ext) for ext in allowed_extensions):
        return RedirectResponse(
            url=f"/ark/servers/{server_id}/backup?error=Érvénytelen+fájlformátum",
            status_code=302
        )
    
    # Backup feltöltése
    backup_file = upload_backup(server_path, file.file, file.filename)
    
    if backup_file:
        return RedirectResponse(
            url=f"/ark/servers/{server_id}/backup?success=Backup+feltöltve",
            status_code=302
        )
    else:
        return RedirectResponse(
            url=f"/ark/servers/{server_id}/backup?error=Backup+feltöltése+sikertelen",
            status_code=302
        )

@router.post("/{server_id}/backup/{backup_name}/restore")
async def restore_backup_endpoint(
    request: Request,
    server_id: int,
    backup_name: str,
    db: Session = Depends(get_db)
):
    """Backup visszaállítása"""
    current_user = require_server_admin(request, db)
    
    # Szerver lekérése
    server = db.query(ServerInstance).filter(
        and_(
            ServerInstance.id == server_id,
            ServerInstance.server_admin_id == current_user.id
        )
    ).first()
    
    if not server:
        raise HTTPException(status_code=404, detail="Szerver nem található")
    
    # Szerver útvonal
    if server.server_path:
        server_path = Path(server.server_path)
    else:
        from app.database import Cluster
        cluster = db.query(Cluster).filter(Cluster.id == server.cluster_id).first()
        if not cluster:
            raise HTTPException(status_code=404, detail="Cluster nem található")
        server_path = get_server_path(server.id, cluster.cluster_id, server.server_admin_id)
    
    # Backup visszaállítása
    success = restore_backup(server_path, backup_name)
    
    if success:
        return RedirectResponse(
            url=f"/ark/servers/{server_id}/backup?success=Backup+visszaállítva",
            status_code=302
        )
    else:
        return RedirectResponse(
            url=f"/ark/servers/{server_id}/backup?error=Backup+visszaállítása+sikertelen",
            status_code=302
        )

@router.post("/{server_id}/backup/{backup_name}/delete")
async def delete_backup_endpoint(
    request: Request,
    server_id: int,
    backup_name: str,
    db: Session = Depends(get_db)
):
    """Backup törlése"""
    current_user = require_server_admin(request, db)
    
    # Szerver lekérése
    server = db.query(ServerInstance).filter(
        and_(
            ServerInstance.id == server_id,
            ServerInstance.server_admin_id == current_user.id
        )
    ).first()
    
    if not server:
        raise HTTPException(status_code=404, detail="Szerver nem található")
    
    # Szerver útvonal
    if server.server_path:
        server_path = Path(server.server_path)
    else:
        from app.database import Cluster
        cluster = db.query(Cluster).filter(Cluster.id == server.cluster_id).first()
        if not cluster:
            raise HTTPException(status_code=404, detail="Cluster nem található")
        server_path = get_server_path(server.id, cluster.cluster_id, server.server_admin_id)
    
    # Backup törlése
    success = delete_backup(server_path, backup_name)
    
    if success:
        return RedirectResponse(
            url=f"/ark/servers/{server_id}/backup?success=Backup+törölve",
            status_code=302
        )
    else:
        return RedirectResponse(
            url=f"/ark/servers/{server_id}/backup?error=Backup+törlése+sikertelen",
            status_code=302
        )


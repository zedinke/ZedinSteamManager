"""
Ark Server Files router - Server Admin szerverfájlok telepítése/törlése
"""

from fastapi import APIRouter, Request, Form, HTTPException, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from app.database import get_db, User, UserServerFiles
from app.services.ark_install_service import install_ark_server_files, delete_ark_server_files
from app.services.symlink_service import get_user_serverfiles_path
from fastapi.templating import Jinja2Templates
from pathlib import Path
from datetime import datetime
import json
import asyncio
import uuid

router = APIRouter(prefix="/ark/serverfiles", tags=["ark_serverfiles"])

# Template-ek inicializálása
BASE_DIR = Path(__file__).parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Aktív telepítések tárolása (session_id -> task)
active_installations = {}

def require_server_admin(request: Request, db: Session = Depends(get_db)) -> User:
    """Server Admin jogosultság ellenőrzése"""
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=302,
            detail="Nincs bejelentkezve",
            headers={"Location": "/login"}
        )
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user or user.role.value not in ["server_admin", "manager_admin"]:
        raise HTTPException(
            status_code=403,
            detail="Nincs jogosultságod - Server Admin szükséges"
        )
    return user

@router.get("", response_class=HTMLResponse)
async def list_serverfiles(
    request: Request,
    db: Session = Depends(get_db)
):
    """Server Admin: Szerverfájlok listája"""
    current_user = require_server_admin(request, db)
    
    # Felhasználó szerverfájljainak lekérése
    serverfiles = db.query(UserServerFiles).filter(
        UserServerFiles.user_id == current_user.id
    ).order_by(desc(UserServerFiles.installed_at)).all()
    
    return templates.TemplateResponse("ark/serverfiles/list.html", {
        "request": request,
        "current_user": current_user,
        "serverfiles": serverfiles
    })

@router.get("/install", response_class=HTMLResponse)
async def show_install_form(
    request: Request,
    db: Session = Depends(get_db)
):
    """Server Admin: Szerverfájlok telepítési form"""
    current_user = require_server_admin(request, db)
    
    return templates.TemplateResponse("ark/serverfiles/install.html", {
        "request": request,
        "current_user": current_user
    })

@router.post("/install")
async def start_install(
    request: Request,
    db: Session = Depends(get_db)
):
    """Server Admin: Szerverfájlok telepítés indítása (mindig legfrissebb verzió)"""
    current_user = require_server_admin(request, db)
    
    # Mindig "latest" verziót használunk
    version = "latest"
    
    # Telepítési útvonal
    user_serverfiles = get_user_serverfiles_path(current_user.id)
    install_path = user_serverfiles / version
    
    # Ellenőrizzük, hogy van-e már telepítés folyamatban
    existing_pending = db.query(UserServerFiles).filter(
        and_(
            UserServerFiles.user_id == current_user.id,
            UserServerFiles.version == version,
            UserServerFiles.installation_status.in_(["pending", "installing"])
        )
    ).first()
    
    if existing_pending:
        raise HTTPException(
            status_code=400,
            detail="Már van telepítés folyamatban. Várj, amíg befejeződik!"
        )
    
    # Ha van már "latest" verzió, akkor újratelepítésként kezeljük
    # (a régi verziót töröljük, ha nincs aktív)
    existing = db.query(UserServerFiles).filter(
        and_(
            UserServerFiles.user_id == current_user.id,
            UserServerFiles.version == version
        )
    ).first()
    
    if existing and not existing.is_active:
        # Ha nem aktív, töröljük a régi rekordot
        install_path_obj = Path(existing.install_path)
        if install_path_obj.exists():
            delete_ark_server_files(install_path_obj)
        db.delete(existing)
        db.commit()
    
    # Új rekord létrehozása
    serverfiles = UserServerFiles(
        user_id=current_user.id,
        version=version,
        install_path=str(install_path.absolute()),
        is_active=False,
        installed_by_id=current_user.id,
        installation_status="pending"
    )
    
    db.add(serverfiles)
    db.commit()
    db.refresh(serverfiles)
    
    # Session ID generálása
    session_id = str(uuid.uuid4())
    
    return JSONResponse({
        "success": True,
        "session_id": session_id,
        "serverfiles_id": serverfiles.id,
        "message": "Telepítés elindítva"
    })

@router.websocket("/install/{serverfiles_id}/stream")
async def install_stream(websocket: WebSocket, serverfiles_id: int):
    """WebSocket endpoint a telepítési folyamat streameléséhez"""
    await websocket.accept()
    
    db = next(get_db())
    serverfiles = None
    
    try:
        # Szerverfájlok rekord lekérése
        serverfiles = db.query(UserServerFiles).filter(
            UserServerFiles.id == serverfiles_id
        ).first()
        
        if not serverfiles:
            await websocket.send_json({"error": "Szerverfájlok rekord nem található"})
            await websocket.close()
            return
        
        # Felhasználó ellenőrzése
        user = db.query(User).filter(User.id == serverfiles.user_id).first()
        if not user:
            await websocket.send_json({"error": "Felhasználó nem található"})
            await websocket.close()
            return
        
        # Telepítési útvonal
        install_path = Path(serverfiles.install_path)
        
        # Státusz frissítése
        serverfiles.installation_status = "installing"
        db.commit()
        
        # Progress callback
        log_lines = []
        
        async def progress_callback(message: str):
            log_lines.append(message)
            try:
                await websocket.send_json({
                    "type": "progress",
                    "message": message
                })
            except:
                pass  # Ha a WebSocket már bezárult, ne dobjunk hibát
        
        # Telepítés indítása
        await websocket.send_json({
            "type": "start",
            "message": "Telepítés elindítva..."
        })
        
        success, log = await install_ark_server_files(
            str(user.id),  # user_id stringként
            serverfiles.version,
            install_path,
            progress_callback
        )
        
        # Státusz és log frissítése - új session használata a hosszú folyamat után
        db.close()
        db = next(get_db())
        
        # Újra lekérdezzük a rekordot
        serverfiles = db.query(UserServerFiles).filter(
            UserServerFiles.id == serverfiles_id
        ).first()
        
        if serverfiles:
            serverfiles.installation_status = "completed" if success else "failed"
            serverfiles.installation_log = log
            
            # Ha sikeres és nincs aktív verzió, akkor aktiváljuk
            if success:
                existing_active = db.query(UserServerFiles).filter(
                    and_(
                        UserServerFiles.user_id == serverfiles.user_id,
                        UserServerFiles.is_active == True,
                        UserServerFiles.id != serverfiles.id
                    )
                ).first()
                
                if not existing_active:
                    serverfiles.is_active = True
            
            db.commit()
        
        # Végleges üzenet
        await websocket.send_json({
            "type": "complete",
            "success": success,
            "message": "Telepítés befejezve" if success else "Telepítés sikertelen"
        })
        
    except Exception as e:
        await websocket.send_json({
            "type": "error",
            "message": f"Hiba: {str(e)}"
        })
        
        # Státusz frissítése
        if serverfiles:
            db.close()
            db = next(get_db())
            serverfiles = db.query(UserServerFiles).filter(
                UserServerFiles.id == serverfiles_id
            ).first()
            if serverfiles:
                serverfiles.installation_status = "failed"
                serverfiles.installation_log = f"Hiba: {str(e)}"
                db.commit()
    
    finally:
        db.close()
        await websocket.close()

@router.post("/{serverfiles_id}/delete")
async def delete_serverfiles(
    request: Request,
    serverfiles_id: int,
    db: Session = Depends(get_db)
):
    """Server Admin: Szerverfájlok törlése"""
    current_user = require_server_admin(request, db)
    
    serverfiles = db.query(UserServerFiles).filter(
        UserServerFiles.id == serverfiles_id
    ).first()
    
    if not serverfiles:
        raise HTTPException(status_code=404, detail="Szerverfájlok nem találhatók")
    
    # Felhasználó ellenőrzése
    if serverfiles.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Nincs jogosultságod")
    
    if serverfiles.is_active:
        return RedirectResponse(
            url=f"/ark/serverfiles?error=Az+aktív+verzió+nem+törölhető.+Először+aktiválj+egy+másik+verziót!",
            status_code=302
        )
    
    # Fájlok törlése
    install_path = Path(serverfiles.install_path)
    if install_path.exists():
        delete_ark_server_files(install_path)
    
    # Rekord törlése
    db.delete(serverfiles)
    db.commit()
    
    return RedirectResponse(
        url=f"/ark/serverfiles?success=Szerverfájlok+sikeresen+törölve",
        status_code=302
    )

@router.post("/{serverfiles_id}/activate")
async def activate_serverfiles(
    request: Request,
    serverfiles_id: int,
    db: Session = Depends(get_db)
):
    """Server Admin: Szerverfájlok aktiválása"""
    current_user = require_server_admin(request, db)
    
    serverfiles = db.query(UserServerFiles).filter(
        UserServerFiles.id == serverfiles_id
    ).first()
    
    if not serverfiles:
        raise HTTPException(status_code=404, detail="Szerverfájlok nem találhatók")
    
    # Felhasználó ellenőrzése
    if serverfiles.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Nincs jogosultságod")
    
    if serverfiles.installation_status != "completed":
        raise HTTPException(
            status_code=400,
            detail="Csak a sikeresen telepített verziók aktiválhatók"
        )
    
    # Összes aktív deaktiválása ugyanahhoz a felhasználóhoz
    db.query(UserServerFiles).filter(
        and_(
            UserServerFiles.user_id == current_user.id,
            UserServerFiles.is_active == True
        )
    ).update({"is_active": False})
    
    # Új aktiválása
    serverfiles.is_active = True
    db.commit()
    
    return JSONResponse({
        "success": True,
        "message": "Szerverfájlok aktiválva"
    })


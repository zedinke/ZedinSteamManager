"""
Ark Survival Evolved Server Files router - Server Admin szerverfájlok telepítése/törlése
"""

from fastapi import APIRouter, Request, Form, HTTPException, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from app.database import get_db, User, UserServerFiles, SessionLocal, Game
from app.services.ark_install_service import install_ark_server_files, delete_ark_server_files, check_for_updates
from app.services.symlink_service import get_user_serverfiles_path
from fastapi.templating import Jinja2Templates
from pathlib import Path
from datetime import datetime
import json
import asyncio
import uuid

router = APIRouter(prefix="/ark-evolved/serverfiles", tags=["ark_evolved_serverfiles"])

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
    
    # Aktív szerverfájlok ellenőrzése frissítésre
    # Megjegyzés: A frissítés ellenőrzés hosszú ideig tart, ezért nem blokkoljuk a listázást
    # A frissítés ellenőrzés külön endpoint-on történik vagy háttérben
    has_update = False
    active_serverfiles = None
    if serverfiles:
        active_serverfiles = next((sf for sf in serverfiles if sf.is_active and sf.installation_status == "completed"), None)
        # A frissítés ellenőrzés kikapcsolva a listázásnál, mert túl hosszú
        # Külön endpoint-on lehet ellenőrizni: /ark-evolved/serverfiles/check-updates
    
    return templates.TemplateResponse("ark_evolved/serverfiles/list.html", {
        "request": request,
        "current_user": current_user,
        "serverfiles": serverfiles,
        "has_update": has_update,
        "active_serverfiles": active_serverfiles
    })

@router.get("/install", response_class=HTMLResponse)
async def show_install_form(
    request: Request,
    update: int = None,
    db: Session = Depends(get_db)
):
    """Server Admin: Szerverfájlok telepítési form"""
    current_user = require_server_admin(request, db)
    
    # Ha update paraméter van, akkor automatikusan indítsuk a streamelést
    serverfiles_id = update
    
    return templates.TemplateResponse("ark_evolved/serverfiles/install.html", {
        "request": request,
        "current_user": current_user,
        "serverfiles_id": serverfiles_id,
        "is_update": update is not None
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
    
    # Ark Survival Evolved játék lekérése az adatbázisból
    ark_game = db.query(Game).filter(Game.name == "Ark Survival Evolved").first()
    if not ark_game:
        # Ha nincs találat, próbáljuk meg case-insensitive kereséssel
        ark_game = db.query(Game).filter(Game.name.ilike("%ark%evolved%")).first()
    
    # FONTOS: Ez az ark_evolved_serverfiles router, tehát MINDIG az Ark Evolved útvonalat használjuk
    # Ha nincs játék az adatbázisban, akkor is az Evolved útvonalat használjuk
    from app.config import settings
    base_path = Path(settings.ark_evolved_serverfiles_base)
    user_serverfiles = base_path / f"user_{current_user.id}"
    install_path = user_serverfiles / version
    
    # Debug log
    import logging
    logger = logging.getLogger(__name__)
    if ark_game:
        logger.info(f"start_install: Found Ark Survival Evolved game: id={ark_game.id}, name={ark_game.name}, is_active={ark_game.is_active}")
    else:
        logger.warning(f"start_install: Ark Survival Evolved game NOT FOUND in database, but using Evolved path anyway (this is ark_evolved_serverfiles router)")
        # Listázuk az összes Ark játékot debug céljából
        all_ark_games = db.query(Game).filter(Game.name.ilike("%ark%")).all()
        logger.warning(f"start_install: All Ark games in database: {[(g.id, g.name, g.is_active) for g in all_ark_games]}")
    
    logger.info(f"start_install: Using Ark Evolved base path: {base_path}")
    logger.info(f"start_install: Calculated install_path: {install_path}")
    
    logger.info(f"start_install: Calculated install_path: {install_path}")
    
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
        
        # Státusz frissítése (commit előtt)
        serverfiles.installation_status = "installing"
        try:
            db.commit()
        except Exception as commit_error:
            # Ha a commit sikertelen, próbáljuk újra egy új session-nel
            db.rollback()
            db.close()
            db = SessionLocal()
            serverfiles = db.query(UserServerFiles).filter(
                UserServerFiles.id == serverfiles_id
            ).first()
            if serverfiles:
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
        
        # Ark Survival Evolved játék lekérése az adatbázisból
        ark_game = db.query(Game).filter(Game.name == "Ark Survival Evolved").first()
        steam_app_id = None
        if ark_game and ark_game.steam_app_id:
            steam_app_id = ark_game.steam_app_id
            await progress_callback(f"Játék: {ark_game.name} (Steam App ID: {steam_app_id})")
        else:
            # Alapértelmezett: Ark Survival Evolved
            steam_app_id = "346110"
            await progress_callback(f"Játék: Ark Survival Evolved (alapértelmezett Steam App ID: {steam_app_id})")
        
        # Telepítés vagy frissítés
        success, log = await install_ark_server_files(
            str(user.id),  # user_id stringként
            serverfiles.version,
            install_path,
            progress_callback,
            steam_app_id=steam_app_id
        )
        
        # Státusz és log frissítése - új session használata a hosszú folyamat után
        try:
            db.commit()
        except:
            pass
        
        db.close()
        
        # Új session létrehozása
        from app.database import SessionLocal
        new_db = SessionLocal()
        
        try:
            # Újra lekérdezzük a rekordot
            serverfiles = new_db.query(UserServerFiles).filter(
                UserServerFiles.id == serverfiles_id
            ).first()
            
            if serverfiles:
                serverfiles.installation_status = "completed" if success else "failed"
                serverfiles.installation_log = log
                
                # Ha sikeres és nincs aktív verzió, akkor aktiváljuk
                if success:
                    existing_active = new_db.query(UserServerFiles).filter(
                        and_(
                            UserServerFiles.user_id == serverfiles.user_id,
                            UserServerFiles.is_active == True,
                            UserServerFiles.id != serverfiles.id
                        )
                    ).first()
                    
                    if not existing_active:
                        serverfiles.is_active = True
                
                new_db.commit()
        except Exception as e:
            new_db.rollback()
            await websocket.send_json({
                "type": "error",
                "message": f"Adatbázis hiba a státusz frissítésekor: {str(e)}"
            })
        finally:
            new_db.close()
        
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
            try:
                db.commit()
            except:
                pass
            db.close()
            
            # Új session létrehozása
            from app.database import SessionLocal
            new_db = SessionLocal()
            try:
                serverfiles = new_db.query(UserServerFiles).filter(
                    UserServerFiles.id == serverfiles_id
                ).first()
                if serverfiles:
                    serverfiles.installation_status = "failed"
                    serverfiles.installation_log = f"Hiba: {str(e)}"
                    new_db.commit()
            except:
                new_db.rollback()
            finally:
                new_db.close()
    
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
    
    # Ha aktív verzió, próbáljuk aktiválni egy másik verziót (ha van)
    if serverfiles.is_active:
        # Ellenőrizzük, hogy van-e másik completed verzió
        other_completed = db.query(UserServerFiles).filter(
            and_(
                UserServerFiles.user_id == current_user.id,
                UserServerFiles.id != serverfiles.id,
                UserServerFiles.installation_status == "completed"
            )
        ).order_by(UserServerFiles.installed_at.desc()).first()
        
        if other_completed:
            # Ha van másik completed verzió, aktiváljuk azt
            other_completed.is_active = True
            serverfiles.is_active = False
            db.commit()
        else:
            # Ha nincs másik verzió, akkor is törölhetjük (de nincs aktív verzió)
            serverfiles.is_active = False
            db.commit()
    
    # Fájlok törlése
    install_path = Path(serverfiles.install_path)
    if install_path.exists():
        delete_ark_server_files(install_path)
    
    # Rekord törlése
    db.delete(serverfiles)
    db.commit()
    
    return RedirectResponse(
        url=f"/ark-evolved/serverfiles?success=Szerverfájlok+sikeresen+törölve",
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
    
    return RedirectResponse(
        url=f"/ark-evolved/serverfiles?success=Szerverfájlok+sikeresen+aktiválva",
        status_code=302
    )

@router.get("/check-updates")
async def check_updates_api(
    request: Request,
    db: Session = Depends(get_db)
):
    """Server Admin: Frissítés ellenőrzése API endpoint"""
    current_user = require_server_admin(request, db)
    
    # Aktív szerverfájlok lekérése
    active_serverfiles = db.query(UserServerFiles).filter(
        and_(
            UserServerFiles.user_id == current_user.id,
            UserServerFiles.is_active == True,
            UserServerFiles.installation_status == "completed"
        )
    ).first()
    
    if not active_serverfiles:
        return JSONResponse({
            "has_update": False,
            "message": "Nincs aktív szerverfájl telepítve"
        })
    
    install_path = Path(active_serverfiles.install_path)
    if not install_path.exists():
        return JSONResponse({
            "has_update": True,
            "message": "Telepítési útvonal nem létezik"
        })
    
    # Frissítés ellenőrzése (hosszú művelet, de külön endpoint)
    try:
        # Ark játék lekérése az adatbázisból
        ark_game = db.query(Game).filter(Game.name == "Ark Survival Evolved").first()
        steam_app_id = None
        if ark_game and ark_game.steam_app_id:
            steam_app_id = ark_game.steam_app_id
        
        has_update, _ = await check_for_updates(install_path, steam_app_id=steam_app_id)
        return JSONResponse({
            "has_update": has_update,
            "message": "Frissítés elérhető" if has_update else "Nincs frissítés"
        })
    except Exception as e:
        return JSONResponse({
            "has_update": False,
            "message": f"Ellenőrzési hiba: {str(e)}"
        })

@router.post("/update")
async def start_update(
    request: Request,
    db: Session = Depends(get_db)
):
    """Server Admin: Szerverfájlok frissítése (legfrissebb verzió)"""
    current_user = require_server_admin(request, db)
    
    # Aktív szerverfájlok lekérése
    active_serverfiles = db.query(UserServerFiles).filter(
        and_(
            UserServerFiles.user_id == current_user.id,
            UserServerFiles.is_active == True,
            UserServerFiles.installation_status == "completed"
        )
    ).first()
    
    if not active_serverfiles:
        raise HTTPException(
            status_code=400,
            detail="Nincs aktív szerverfájl telepítve. Először telepíts egyet!"
        )
    
    # Ellenőrizzük, hogy van-e már telepítés folyamatban
    existing_pending = db.query(UserServerFiles).filter(
        and_(
            UserServerFiles.user_id == current_user.id,
            UserServerFiles.version == "latest",
            UserServerFiles.installation_status.in_(["pending", "installing"])
        )
    ).first()
    
    if existing_pending:
        raise HTTPException(
            status_code=400,
            detail="Már van telepítés/frissítés folyamatban. Várj, amíg befejeződik!"
        )
    
    # Telepítési útvonal
    # FONTOS: Ez az ark_evolved_serverfiles router, tehát MINDIG az Ark Evolved útvonalat használjuk
    from app.config import settings
    from pathlib import Path
    base_path = Path(settings.ark_evolved_serverfiles_base)
    user_serverfiles = base_path / f"user_{current_user.id}"
    install_path = user_serverfiles / "latest"
    
    # Új rekord létrehozása frissítéshez
    serverfiles = UserServerFiles(
        user_id=current_user.id,
        version="latest",
        install_path=str(install_path.absolute()),
        is_active=False,
        installed_by_id=current_user.id,
        installation_status="pending"
    )
    
    db.add(serverfiles)
    db.commit()
    db.refresh(serverfiles)
    
    return JSONResponse({
        "success": True,
        "serverfiles_id": serverfiles.id,
        "message": "Frissítés elindítva"
    })

@router.get("/{serverfiles_id}/verify")
async def verify_installation(
    request: Request,
    serverfiles_id: int,
    db: Session = Depends(get_db)
):
    """Server Admin: Szerverfájlok telepítés ellenőrzése"""
    current_user = require_server_admin(request, db)
    
    serverfiles = db.query(UserServerFiles).filter(
        UserServerFiles.id == serverfiles_id
    ).first()
    
    if not serverfiles:
        raise HTTPException(status_code=404, detail="Szerverfájlok nem találhatók")
    
    if serverfiles.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Nincs jogosultságod")
    
    install_path = Path(serverfiles.install_path)
    binary_path = install_path / "ShooterGame" / "Binaries" / "Linux" / "ShooterGameServer"
    
    result = {
        "install_path": str(install_path),
        "install_path_exists": install_path.exists(),
        "binary_path": str(binary_path),
        "binary_exists": binary_path.exists(),
        "details": {}
    }
    
    if install_path.exists():
        result["details"]["install_path_contents"] = [item.name for item in install_path.iterdir()][:20]
        
        shooter_game = install_path / "ShooterGame"
        if shooter_game.exists():
            result["details"]["shooter_game_exists"] = True
            result["details"]["shooter_game_contents"] = [item.name for item in shooter_game.iterdir()][:20]
            
            binaries = shooter_game / "Binaries"
            if binaries.exists():
                result["details"]["binaries_exists"] = True
                result["details"]["binaries_contents"] = [item.name for item in binaries.iterdir()]
                
                linux_bin = binaries / "Linux"
                if linux_bin.exists():
                    result["details"]["linux_exists"] = True
                    result["details"]["linux_contents"] = [item.name for item in linux_bin.iterdir()][:20]
                else:
                    result["details"]["linux_exists"] = False
                    result["details"]["binaries_subdirs"] = [item.name for item in binaries.iterdir() if item.is_dir()]
            else:
                result["details"]["binaries_exists"] = False
        else:
            result["details"]["shooter_game_exists"] = False
    
    return JSONResponse(result)


"""
Ark Server Admin router - Manager Admin szerverfájlok telepítése
"""

from fastapi import APIRouter, Request, Form, HTTPException, Depends, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db, User, ArkServerFiles
from app.dependencies import require_manager_admin
from fastapi.templating import Jinja2Templates
from pathlib import Path
from datetime import datetime
import shutil
import os

router = APIRouter(prefix="/admin/ark", tags=["ark_admin"])

# Template-ek inicializálása
BASE_DIR = Path(__file__).parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

@router.get("/files", response_class=HTMLResponse)
async def list_ark_files(
    request: Request,
    db: Session = Depends(get_db)
):
    """Manager Admin: Ark szerverfájlok listája"""
    current_user = require_manager_admin(request, db)
    
    ark_files = db.query(ArkServerFiles).order_by(ArkServerFiles.installed_at.desc()).all()
    
    return templates.TemplateResponse("admin/ark/files.html", {
        "request": request,
        "current_user": current_user,
        "ark_files": ark_files
    })

@router.get("/files/install", response_class=HTMLResponse)
async def show_install_form(
    request: Request,
    db: Session = Depends(get_db)
):
    """Manager Admin: Ark szerverfájlok telepítési form"""
    current_user = require_manager_admin(request, db)
    
    return templates.TemplateResponse("admin/ark/install.html", {
        "request": request,
        "current_user": current_user
    })

@router.post("/files/install")
async def install_ark_files(
    request: Request,
    version: str = Form(...),
    install_path: str = Form(...),
    notes: str = Form(None),
    db: Session = Depends(get_db)
):
    """Manager Admin: Ark szerverfájlok telepítése"""
    current_user = require_manager_admin(request, db)
    
    # Útvonal ellenőrzése
    install_path_obj = Path(install_path)
    if not install_path_obj.exists() or not install_path_obj.is_dir():
        raise HTTPException(
            status_code=400,
            detail="A megadott útvonal nem létezik vagy nem könyvtár"
        )
    
    # Ellenőrizzük, hogy van-e már aktív verzió
    existing_active = db.query(ArkServerFiles).filter(
        ArkServerFiles.is_active == True
    ).first()
    
    # Új rekord létrehozása
    ark_files = ArkServerFiles(
        version=version,
        install_path=str(install_path_obj.absolute()),
        is_active=True if not existing_active else False,  # Ha van aktív, akkor inaktívként hozzuk létre
        installed_by_id=current_user.id,
        notes=notes
    )
    
    db.add(ark_files)
    db.commit()
    db.refresh(ark_files)
    
    return RedirectResponse(
        url="/admin/ark/files?success=Ark+szerverfájlok+telepítve",
        status_code=302
    )

@router.post("/files/{file_id}/activate")
async def activate_ark_files(
    request: Request,
    file_id: int,
    db: Session = Depends(get_db)
):
    """Manager Admin: Ark szerverfájlok aktiválása"""
    current_user = require_manager_admin(request, db)
    
    ark_files = db.query(ArkServerFiles).filter(ArkServerFiles.id == file_id).first()
    if not ark_files:
        raise HTTPException(status_code=404, detail="Ark szerverfájlok nem találhatók")
    
    # Összes aktív deaktiválása
    db.query(ArkServerFiles).filter(ArkServerFiles.is_active == True).update({
        "is_active": False
    })
    
    # Új aktiválása
    ark_files.is_active = True
    db.commit()
    
    return JSONResponse({
        "success": True,
        "message": "Ark szerverfájlok aktiválva"
    })

@router.post("/files/{file_id}/delete")
async def delete_ark_files(
    request: Request,
    file_id: int,
    db: Session = Depends(get_db)
):
    """Manager Admin: Ark szerverfájlok törlése"""
    current_user = require_manager_admin(request, db)
    
    ark_files = db.query(ArkServerFiles).filter(ArkServerFiles.id == file_id).first()
    if not ark_files:
        raise HTTPException(status_code=404, detail="Ark szerverfájlok nem találhatók")
    
    if ark_files.is_active:
        return RedirectResponse(
            url=f"/admin/ark/files?error=Az+aktív+verzió+nem+törölhető.+Először+aktiválj+egy+másik+verziót!",
            status_code=302
        )
    
    # Fájlok törlése
    install_path = Path(ark_files.install_path)
    if install_path.exists():
        try:
            import shutil
            shutil.rmtree(install_path)
        except Exception as e:
            # Ha a fájlok törlése sikertelen, csak logoljuk, de folytatjuk a rekord törlését
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Szerverfájlok törlése sikertelen: {e}")
    
    # Rekord törlése
    db.delete(ark_files)
    db.commit()
    
    return RedirectResponse(
        url=f"/admin/ark/files?success=Ark+szerverfájlok+sikeresen+törölve",
        status_code=302
    )


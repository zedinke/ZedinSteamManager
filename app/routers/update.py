"""
Update router - Manager Admin funkciók
"""

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies import require_manager_admin
from pathlib import Path
import subprocess
import os
import json

router = APIRouter(prefix="/admin/update", tags=["update"])

@router.get("", response_class=HTMLResponse)
async def update_page(request: Request, db: Session = get_db()):
    """Update oldal megjelenítése"""
    # Manager Admin ellenőrzés
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    
    try:
        await require_manager_admin(request, db)
    except HTTPException:
        return RedirectResponse(url="/dashboard", status_code=302)
    
    from jinja2 import Template
    
    template_path = Path(__file__).parent.parent.parent / "templates" / "admin" / "update.html"
    with open(template_path, "r", encoding="utf-8") as f:
        template = Template(f.read())
    
    # Git információk lekérése
    project_dir = Path(__file__).parent.parent.parent
    git_info = get_git_info(project_dir)
    
    return HTMLResponse(content=template.render(
        request=request,
        git_info=git_info,
        is_updating=is_update_in_progress()
    ))

@router.post("/check")
async def check_update(request: Request, db: Session = get_db()):
    """Git update ellenőrzése"""
    # Manager Admin ellenőrzés
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Nincs bejelentkezve")
    
    try:
        await require_manager_admin(request, db)
    except HTTPException:
        raise HTTPException(status_code=403, detail="Nincs jogosultság")
    
    project_dir = Path(__file__).parent.parent.parent
    
    try:
        # Git fetch
        result = subprocess.run(
            ["git", "fetch", "origin", "main"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        # Git log ellenőrzése
        result = subprocess.run(
            ["git", "log", "HEAD..origin/main", "--oneline"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        has_update = len(result.stdout.strip()) > 0
        commits = result.stdout.strip().split("\n") if has_update else []
        
        return JSONResponse(content={
            "has_update": has_update,
            "commits": commits[:10],  # Legutóbbi 10 commit
            "commit_count": len(commits)
        })
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )

@router.post("/execute")
async def execute_update(request: Request, db: Session = get_db()):
    """Update végrehajtása"""
    # Manager Admin ellenőrzés
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Nincs bejelentkezve")
    
    try:
        await require_manager_admin(request, db)
    except HTTPException:
        raise HTTPException(status_code=403, detail="Nincs jogosultság")
    
    # Update már folyamatban van?
    if is_update_in_progress():
        return JSONResponse(
            status_code=400,
            content={"error": "Update már folyamatban van"}
        )
    
    # Update flag beállítása
    set_update_in_progress(True)
    
    project_dir = Path(__file__).parent.parent.parent
    update_script = project_dir / "scripts" / "update.sh"
    
    if not update_script.exists():
        set_update_in_progress(False)
        return JSONResponse(
            status_code=500,
            content={"error": "Update script nem található"}
        )
    
    try:
        # Update script futtatása háttérben
        subprocess.Popen(
            ["bash", str(update_script)],
            cwd=project_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        return JSONResponse(content={
            "success": True,
            "message": "Update elindítva"
        })
    except Exception as e:
        set_update_in_progress(False)
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )

@router.get("/status")
async def update_status(request: Request):
    """Update státusz ellenőrzése"""
    project_dir = Path(__file__).parent.parent.parent
    
    # Service státusz ellenőrzése
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "zedinarkmanager"],
            capture_output=True,
            text=True,
            timeout=5
        )
        service_active = result.returncode == 0
    except:
        service_active = False
    
    # Update folyamatban van?
    updating = is_update_in_progress()
    
    # Ha a service aktív és nincs update folyamatban, akkor kész
    if service_active and not updating:
        set_update_in_progress(False)
    
    return JSONResponse(content={
        "service_active": service_active,
        "updating": updating
    })

def get_git_info(project_dir: Path) -> dict:
    """Git információk lekérése"""
    try:
        # Jelenlegi branch
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=5
        )
        current_branch = result.stdout.strip() if result.returncode == 0 else "unknown"
        
        # Jelenlegi commit
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=5
        )
        current_commit = result.stdout.strip() if result.returncode == 0 else "unknown"
        
        # Utolsó commit dátum
        result = subprocess.run(
            ["git", "log", "-1", "--format=%cd", "--date=short"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=5
        )
        last_commit_date = result.stdout.strip() if result.returncode == 0 else "unknown"
        
        return {
            "branch": current_branch,
            "commit": current_commit,
            "last_commit_date": last_commit_date
        }
    except:
        return {
            "branch": "unknown",
            "commit": "unknown",
            "last_commit_date": "unknown"
        }

def is_update_in_progress() -> bool:
    """Update folyamatban van-e?"""
    project_dir = Path(__file__).parent.parent.parent
    flag_file = project_dir / ".updating"
    return flag_file.exists()

def set_update_in_progress(value: bool):
    """Update flag beállítása"""
    project_dir = Path(__file__).parent.parent.parent
    flag_file = project_dir / ".updating"
    
    if value:
        flag_file.touch()
    else:
        if flag_file.exists():
            flag_file.unlink()


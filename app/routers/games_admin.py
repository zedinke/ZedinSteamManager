"""
Games Admin router - Manager Admin játékkezelés
"""

from fastapi import APIRouter, Request, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.database import get_db, User, Game
from app.dependencies import require_manager_admin
from fastapi.templating import Jinja2Templates
from pathlib import Path

router = APIRouter(prefix="/admin/games", tags=["games_admin"])

# Template-ek inicializálása
BASE_DIR = Path(__file__).parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

@router.get("", response_class=HTMLResponse)
async def list_games(
    request: Request,
    db: Session = Depends(get_db)
):
    """Manager Admin: Játékok listája"""
    current_user = require_manager_admin(request, db)
    
    games = db.query(Game).order_by(desc(Game.created_at)).all()
    
    return templates.TemplateResponse("admin/games/list.html", {
        "request": request,
        "current_user": current_user,
        "games": games
    })

@router.get("/add", response_class=HTMLResponse)
async def show_add_game(
    request: Request,
    db: Session = Depends(get_db)
):
    """Manager Admin: Játék hozzáadása form"""
    current_user = require_manager_admin(request, db)
    
    return templates.TemplateResponse("admin/games/add.html", {
        "request": request,
        "current_user": current_user
    })

@router.post("/add")
async def add_game(
    request: Request,
    name: str = Form(...),
    steam_app_id: str = Form(None),
    description: str = Form(None),
    db: Session = Depends(get_db)
):
    """Manager Admin: Játék hozzáadása"""
    current_user = require_manager_admin(request, db)
    
    # Ellenőrizzük, hogy már létezik-e
    existing = db.query(Game).filter(Game.name == name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Ez a játék már létezik")
    
    # Új játék létrehozása
    game = Game(
        name=name,
        steam_app_id=steam_app_id if steam_app_id else None,
        description=description if description else None,
        is_active=True
    )
    
    db.add(game)
    db.commit()
    db.refresh(game)
    
    return RedirectResponse(url="/admin/games", status_code=303)

@router.post("/{game_id}/toggle")
async def toggle_game(
    request: Request,
    game_id: int,
    db: Session = Depends(get_db)
):
    """Manager Admin: Játék aktiválás/deaktiválás"""
    current_user = require_manager_admin(request, db)
    
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Játék nem található")
    
    game.is_active = not game.is_active
    db.commit()
    
    return JSONResponse({
        "success": True,
        "is_active": game.is_active
    })

@router.post("/{game_id}/delete")
async def delete_game(
    request: Request,
    game_id: int,
    db: Session = Depends(get_db)
):
    """Manager Admin: Játék törlése"""
    current_user = require_manager_admin(request, db)
    
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Játék nem található")
    
    db.delete(game)
    db.commit()
    
    return JSONResponse({
        "success": True,
        "message": "Játék törölve"
    })


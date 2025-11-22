"""
Ark Setup router - Ark játék hozzáadása az adatbázishoz
"""

from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db, User, Game
from app.dependencies import require_manager_admin

router = APIRouter(prefix="/admin/ark", tags=["ark_setup"])

@router.post("/setup-game")
async def setup_ark_game(
    request: Request,
    db: Session = Depends(get_db)
):
    """Manager Admin: Ark Survival Ascended játék hozzáadása az adatbázishoz"""
    current_user = require_manager_admin(request, db)
    
    # Ellenőrizzük, hogy létezik-e már
    existing = db.query(Game).filter(Game.name.ilike("%ark%")).first()
    if existing:
        return JSONResponse({
            "success": True,
            "message": "Ark Survival Ascended játék már létezik",
            "game_id": existing.id
        })
    
    # Új játék létrehozása
    ark_game = Game(
        name="Ark Survival Ascended",
        steam_app_id="2430930",  # Ark Survival Ascended Steam App ID
        description="Ark Survival Ascended - Dedicated Server",
        is_active=True
    )
    
    db.add(ark_game)
    db.commit()
    db.refresh(ark_game)
    
    return JSONResponse({
        "success": True,
        "message": "Ark Survival Ascended játék hozzáadva",
        "game_id": ark_game.id
    })


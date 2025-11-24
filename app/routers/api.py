"""
API router (JSON API endpoint-ok)
"""

from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db, User

router = APIRouter()

@router.get("/session/check-role")
async def check_role(request: Request, db: Session = Depends(get_db)):
    """Session role ellenőrzése és frissítése"""
    user_id = request.session.get("user_id")
    if not user_id:
        return JSONResponse(
            status_code=401,
            content={"success": False, "error": "Nincs bejelentkezve"}
        )
    
    current_user = db.query(User).filter(User.id == user_id).first()
    if not current_user:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "Felhasználó nem található"}
        )
    
    # Ellenőrizzük, hogy változott-e a rang
    current_role = request.session.get("user_role")
    role_changed = current_role != current_user.role.value
    
    if role_changed:
        # Frissítjük a session-t
        request.session["user_role"] = current_user.role.value
    
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "role": current_user.role.value,
            "role_changed": role_changed,
            "username": current_user.username
        }
    )


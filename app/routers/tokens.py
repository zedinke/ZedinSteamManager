"""
Token router
"""

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.database import get_db, User, TokenType
from app.dependencies import require_login
from app.database import UserRole
from app.services.token_service import generate_token, activate_token, send_token_to_user
from app.services.notification_service import create_notification
from app.database import Token, User
from app.config import settings

router = APIRouter()

async def require_manager_admin(request: Request, db: Session) -> User:
    """Manager Admin jogosultság ellenőrzése"""
    user_id = request.session.get("user_id")
    if not user_id:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/login", status_code=302)
    
    current_user = db.query(User).filter(User.id == user_id).first()
    if not current_user or current_user.role.value != "manager_admin":
        raise HTTPException(status_code=403, detail="Nincs jogosultságod")
    return current_user

@router.get("/tokens/generate", response_class=HTMLResponse)
async def show_generate(
    request: Request,
    db: Session = Depends(get_db)
):
    """Token generálás oldal"""
    current_user = await require_manager_admin(request, db)
    
    # Összes user és server admin
    users = db.query(User).filter(
        User.role.in_(["user", "server_admin"])
    ).order_by(User.username).all()
    
    from app.main import get_templates
    templates = get_templates()
    return templates.TemplateResponse(
        "tokens/generate.html",
        {"request": request, "users": users}
    )

@router.post("/tokens/generate")
async def generate(
    request: Request,
    user_id: int = Form(...),
    token_type: str = Form(...),
    expires_in_days: int = Form(None),
    db: Session = Depends(get_db)
):
    """Token generálás"""
    current_user = require_manager_admin(request, db)
    
    if token_type not in ["server_admin", "user"]:
        raise HTTPException(status_code=400, detail="Érvénytelen token típus")
    
    token_type_enum = TokenType.SERVER_ADMIN if token_type == "server_admin" else TokenType.USER
    
    token = generate_token(
        db,
        current_user.id,
        token_type_enum,
        expires_in_days or settings.token_expiry_days
    )
    
    # Token küldése
    await send_token_to_user(db, token, user_id)
    
    from app.main import get_templates
    templates = get_templates()
    users = db.query(User).filter(User.role.in_(["user", "server_admin"])).all()
    return templates.TemplateResponse(
        "tokens/generate.html",
        {"request": request, "users": users, "success": "Token sikeresen generálva!"}
    )

@router.get("/tokens/activate", response_class=HTMLResponse)
async def show_activate(request: Request, db: Session = Depends(get_db)):
    """Token aktiválás oldal"""
    from app.main import get_templates
    templates = get_templates()
    return templates.TemplateResponse("tokens/activate.html", {"request": request})

@router.post("/tokens/activate")
async def activate(
    request: Request,
    token: str = Form(...),
    db: Session = Depends(get_db)
):
    """Token aktiválás"""
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    
    result = await activate_token(db, token, user_id)
    
    if result["success"]:
        create_notification(
            db,
            user_id,
            "token_activated",
            "Token aktiválva",
            "Tokenje sikeresen aktiválva lett!"
        )
        
        return RedirectResponse(url="/dashboard", status_code=302)
    else:
        from app.main import get_templates
        templates = get_templates()
        return templates.TemplateResponse(
            "tokens/activate.html",
            {"request": request, "error": result["message"]}
        )

@router.get("/activate-token")
async def activate_by_token(
    request: Request,
    token: str,
    db: Session = Depends(get_db)
):
    """Token aktiválás GET paraméterrel"""
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    
    result = await activate_token(db, token, user_id)
    
    if result["success"]:
        create_notification(
            db,
            user_id,
            "token_activated",
            "Token aktiválva",
            "Tokenje sikeresen aktiválva lett!"
        )
    
    return RedirectResponse(url="/dashboard", status_code=302)


"""
Token router
"""

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.database import get_db, User, TokenType, UserRole
from app.services.token_service import generate_token, activate_token, send_token_to_user
from app.services.notification_service import create_notification
from app.database import Token, User
from app.config import settings

router = APIRouter()

def require_manager_admin(request: Request, db: Session) -> User:
    """Manager Admin jogosultság ellenőrzése"""
    user_id = request.session.get("user_id")
    if not user_id:
        from fastapi.responses import RedirectResponse
        raise HTTPException(status_code=302, detail="Nincs bejelentkezve")
    
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
    current_user = require_manager_admin(request, db)
    
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
    token_count: int = Form(1),
    db: Session = Depends(get_db)
):
    """Token generálás"""
    current_user = require_manager_admin(request, db)
    
    if token_type not in ["server_admin", "user"]:
        raise HTTPException(status_code=400, detail="Érvénytelen token típus")
    
    if token_count < 1 or token_count > 100:
        raise HTTPException(status_code=400, detail="A tokenek száma 1 és 100 között lehet")
    
    token_type_enum = TokenType.SERVER_ADMIN if token_type == "server_admin" else TokenType.USER
    
    # Több token generálása
    generated_tokens = []
    for i in range(token_count):
        token = generate_token(
            db,
            current_user.id,
            token_type_enum,
            expires_in_days or settings.token_expiry_days
        )
        generated_tokens.append(token)
    
    # Tokenek küldése (csak az elsőt küldjük email-ben, a többit csak értesítésben)
    if generated_tokens:
        # Első token email-ben is
        await send_token_to_user(db, generated_tokens[0], user_id)
        
        # További tokenek csak értesítésben
        if len(generated_tokens) > 1:
            from app.services.notification_service import create_notification
            type_text = "Szerver Admin" if token_type_enum == TokenType.SERVER_ADMIN else "Felhasználó"
            from app.config import settings
            from datetime import datetime
            
            tokens_list = "\n".join([f"- {token.token}" for token in generated_tokens[1:]])
            activation_links = "\n".join([f"- {settings.base_url}/tokens/activate?token={token.token}" for token in generated_tokens[1:]])
            
            create_notification(
                db,
                user_id,
                "token_generated",
                f"{len(generated_tokens)} új {type_text} token generálva",
                f"Ön számára {len(generated_tokens)} új {type_text} token lett generálva.\n\nTovábbi tokenek:\n{tokens_list}\n\nAktiválás linkek:\n{activation_links}\n\nLejárat: {generated_tokens[0].expires_at.strftime('%Y-%m-%d %H:%M:%S')}"
            )
    
    from app.main import get_templates
    templates = get_templates()
    users = db.query(User).filter(User.role.in_(["user", "server_admin"])).all()
    
    success_msg = f"{len(generated_tokens)} token sikeresen generálva!"
    if len(generated_tokens) > 1:
        success_msg += f" Az első token email-ben is elküldve, a többi értesítésben."
    
    return templates.TemplateResponse(
        "tokens/generate.html",
        {"request": request, "users": users, "success": success_msg}
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

@router.get("/tokens/list", response_class=HTMLResponse)
async def list_tokens(
    request: Request,
    db: Session = Depends(get_db)
):
    """Tokenek listázása (Manager Admin)"""
    current_user = require_manager_admin(request, db)
    
    # Összes token lekérése
    tokens = db.query(Token).outerjoin(User, Token.user_id == User.id).order_by(Token.created_at.desc()).all()
    
    from app.main import get_templates
    templates = get_templates()
    return templates.TemplateResponse(
        "tokens/list.html",
        {"request": request, "tokens": tokens}
    )

@router.post("/tokens/delete")
async def delete_token(
    request: Request,
    token_id: int = Form(...),
    db: Session = Depends(get_db)
):
    """Token törlése (Manager Admin)"""
    current_user = require_manager_admin(request, db)
    
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        raise HTTPException(status_code=404, detail="Token nem található")
    
    db.delete(token)
    db.commit()
    
    return RedirectResponse(url="/tokens/list?success=Token+sikeresen+törölve", status_code=302)


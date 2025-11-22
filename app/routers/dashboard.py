"""
Dashboard router
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db, User, Token, Server, ServerAdminAdmin, CartItem

router = APIRouter()

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: Session = Depends(get_db)
):
    """Dashboard oldal"""
    # Session ellenőrzés
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    
    current_user = db.query(User).filter(User.id == user_id).first()
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)
    
    stats = {}
    
    if current_user.role.value == "manager_admin":
        from app.database import UserRole
        stats["total_users"] = db.query(func.count(User.id)).scalar()
        stats["server_admins"] = db.query(func.count(User.id)).filter(User.role == UserRole.SERVER_ADMIN).scalar()
        stats["admins"] = db.query(func.count(User.id)).filter(User.role == UserRole.ADMIN).scalar()
        stats["active_tokens"] = db.query(func.count(Token.id)).filter(
            Token.is_active == True,
            Token.expires_at > func.now()
        ).scalar()
    elif current_user.role.value == "server_admin":
        stats["my_servers"] = db.query(func.count(Server.id)).filter(
            Server.server_admin_id == current_user.id
        ).scalar()
        stats["my_admins"] = db.query(func.count(ServerAdminAdmin.id)).filter(
            ServerAdminAdmin.server_admin_id == current_user.id
        ).scalar()
        stats["my_tokens"] = db.query(func.count(Token.id)).filter(
            Token.user_id == current_user.id,
            Token.is_active == True
        ).scalar()
        
        stats["cart_count"] = db.query(func.count(CartItem.id)).filter(
            CartItem.user_id == current_user.id
        ).scalar()
        
        # Tokenek lekérése
        tokens = db.query(Token).filter(Token.user_id == current_user.id).all()
    else:
        tokens = []
    
    from app.main import get_templates
    templates = get_templates()
    return templates.TemplateResponse(
        "dashboard/index.html",
        {
            "request": request,
            "user": current_user,
            "stats": stats,
            "tokens": tokens if current_user.role.value == "server_admin" else []
        }
    )

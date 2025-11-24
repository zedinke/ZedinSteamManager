"""
Admin router
"""

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import (
    get_db, User, ServerAdminAdmin, Server, AdminServer,
    UserRole, Token, CartItem
)
from app.services.auth_service import create_user
from app.services.email_service import send_verification_email
from app.database import Token, User
import secrets
from datetime import datetime, timedelta

router = APIRouter()

@router.get("/admin/list", response_class=HTMLResponse)
async def list_admins(
    request: Request,
    db: Session = Depends(get_db)
):
    """Admin felhasználók listája"""
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    
    current_user = db.query(User).filter(User.id == user_id).first()
    if not current_user or current_user.role.value not in ["manager_admin", "server_admin"]:
        raise HTTPException(status_code=403, detail="Nincs jogosultságod")
    
    if current_user.role.value == "manager_admin":
        # Manager Admin: mindenkit lát
        admins = db.query(User).filter(
            User.role.in_(["server_admin", "admin"])
        ).order_by(User.created_at.desc()).all()
    else:
        # Server Admin: csak az általa létrehozott adminokat
        # Explicit onclause megadása, mert több foreign key van
        admins = db.query(User).join(
            ServerAdminAdmin, 
            ServerAdminAdmin.admin_id == User.id
        ).filter(
            ServerAdminAdmin.server_admin_id == current_user.id,
            User.role == "admin"
        ).order_by(User.created_at.desc()).all()
    
    from app.main import get_templates
    templates = get_templates()
    return templates.TemplateResponse(
        "admin/list.html",
        {"request": request, "admins": admins}
    )

@router.get("/admin/create", response_class=HTMLResponse)
async def show_create_admin(request: Request, db: Session = Depends(get_db)):
    """Admin regisztráció oldal"""
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    
    current_user = db.query(User).filter(User.id == user_id).first()
    if not current_user or current_user.role.value not in ["manager_admin", "server_admin"]:
        raise HTTPException(status_code=403, detail="Nincs jogosultságod")
    
    from app.main import get_templates
    templates = get_templates()
    return templates.TemplateResponse("admin/create.html", {"request": request})

@router.post("/admin/create")
async def create_admin(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    db: Session = Depends(get_db)
):
    """Admin regisztráció"""
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    
    current_user = db.query(User).filter(User.id == user_id).first()
    if not current_user or current_user.role.value not in ["manager_admin", "server_admin"]:
        raise HTTPException(status_code=403, detail="Nincs jogosultságod")
    
    if password != password_confirm:
        from app.main import templates
        return templates.TemplateResponse(
            "admin/create.html",
            {"request": request, "error": "A jelszavak nem egyeznek"}
        )
    
    if len(password) < 8:
        from app.main import templates
        return templates.TemplateResponse(
            "admin/create.html",
            {"request": request, "error": "A jelszónak legalább 8 karakter hosszúnak kell lennie"}
        )
    
    try:
        # Email verifikációs token
        token = secrets.token_urlsafe(32)
        expires = datetime.utcnow() + timedelta(hours=24)
        
        admin = create_user(
            db,
            username,
            email,
            password,
            UserRole.ADMIN,
            current_user.id
        )
        
        # Token beállítása
        admin.email_verification_token = token
        admin.email_verification_expires = expires
        db.commit()
        
        # Kapcsolat létrehozása (ha server_admin hozta létre)
        if current_user.role.value == "server_admin":
            from app.database import ServerAdminAdmin
            relation = ServerAdminAdmin(
                server_admin_id=current_user.id,
                admin_id=admin.id
            )
            db.add(relation)
            db.commit()
        
        # Email küldése
        await send_verification_email(email, username, token)
        
        return RedirectResponse(url="/admin/list", status_code=302)
    except ValueError as e:
        from app.main import templates
        return templates.TemplateResponse(
            "admin/create.html",
            {"request": request, "error": str(e)}
        )

def require_server_admin(request: Request, db: Session) -> User:
    """Server Admin jogosultság ellenőrzése"""
    user_id = request.session.get("user_id")
    if not user_id:
        from fastapi.responses import RedirectResponse
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    
    current_user = db.query(User).filter(User.id == user_id).first()
    if not current_user or current_user.role.value != "server_admin":
        raise HTTPException(status_code=403, detail="Nincs jogosultságod")
    return current_user

@router.post("/admin/delete")
async def delete_admin(
    request: Request,
    admin_id: int = Form(...),
    db: Session = Depends(get_db)
):
    """Admin törlése"""
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    
    current_user = db.query(User).filter(User.id == user_id).first()
    if not current_user or current_user.role.value != "server_admin":
        raise HTTPException(status_code=403, detail="Nincs jogosultságod")
    
    # Ellenőrzés: csak az általa létrehozott adminokat törölheti
    # Explicit onclause megadása, mert több foreign key van
    admin = db.query(User).join(
        ServerAdminAdmin,
        ServerAdminAdmin.admin_id == User.id
    ).filter(
        ServerAdminAdmin.server_admin_id == current_user.id,
        ServerAdminAdmin.admin_id == admin_id,
        User.role == "admin"
    ).first()
    
    if not admin:
        raise HTTPException(status_code=403, detail="Nincs jogosultságod ezt az admint törölni")
    
    db.delete(admin)
    db.commit()
    
    return RedirectResponse(url="/admin/list", status_code=302)

def require_manager_admin(request: Request, db: Session = Depends(get_db)) -> User:
    """Manager Admin jogosultság ellenőrzése"""
    user_id = request.session.get("user_id")
    if not user_id:
        from fastapi.responses import RedirectResponse
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    
    current_user = db.query(User).filter(User.id == user_id).first()
    if not current_user or current_user.role.value != "manager_admin":
        raise HTTPException(status_code=403, detail="Nincs jogosultságod")
    return current_user

@router.get("/admin/users", response_class=HTMLResponse)
async def list_all_users(
    request: Request,
    db: Session = Depends(get_db)
):
    """Manager Admin: összes felhasználó listája"""
    current_user = require_manager_admin(request, db)
    
    from sqlalchemy import func, case
    # MySQL kompatibilis query - FILTER helyett CASE WHEN használata
    results = db.query(
        User,
        func.sum(case((Token.is_active == True, 1), else_=0)).label("active_token_count"),
        func.max(case((Token.is_active == True, Token.expires_at), else_=None)).label("latest_token_expiry")
    ).outerjoin(Token, User.id == Token.user_id).group_by(User.id).order_by(User.created_at.desc()).all()
    
    # Összes Server Admin lekérése (legördülő menühöz)
    server_admins = db.query(User).filter(User.role == UserRole.SERVER_ADMIN).order_by(User.username).all()
    
    # Adatok formázása template-hez
    users = []
    for result in results:
        user = result[0]
        
        # Server Admin kapcsolatok lekérése (ha admin vagy user)
        server_admin_relations = []
        if user.role.value in ["admin", "user"]:
            relations = db.query(ServerAdminAdmin).filter(
                ServerAdminAdmin.admin_id == user.id
            ).all()
            server_admin_relations = [rel.server_admin_id for rel in relations]
        
        users.append({
            "user": user,
            "active_token_count": result.active_token_count or 0,
            "latest_token_expiry": result.latest_token_expiry,
            "server_admin_ids": server_admin_relations
        })
    
    from app.main import get_templates
    templates = get_templates()
    return templates.TemplateResponse(
        "admin/users.html",
        {
            "request": request,
            "users": users,
            "server_admins": server_admins
        }
    )

@router.post("/admin/users/{user_id}/server-admins")
async def update_user_server_admins(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db)
):
    """Felhasználó Server Admin kapcsolatainak frissítése"""
    current_user = require_manager_admin(request, db)
    
    # Form adatok lekérése
    form = await request.form()
    server_admin_ids = []
    for key, value in form.items():
        if key == "server_admin_ids":
            try:
                server_admin_ids.append(int(value))
            except ValueError:
                pass
    
    # Felhasználó lekérése
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Felhasználó nem található")
    
    # Csak admin és user esetén lehet beállítani
    if user.role.value not in ["admin", "user"]:
        raise HTTPException(status_code=400, detail="Csak admin és user felhasználókhoz lehet server admin-okat rendelni")
    
    # Server Admin ID-k ellenőrzése
    if server_admin_ids:
        server_admins = db.query(User).filter(
            User.id.in_(server_admin_ids),
            User.role == UserRole.SERVER_ADMIN
        ).all()
        if len(server_admins) != len(server_admin_ids):
            raise HTTPException(status_code=400, detail="Érvénytelen server admin ID-k")
    
    # Régi kapcsolatok törlése
    db.query(ServerAdminAdmin).filter(
        ServerAdminAdmin.admin_id == user_id
    ).delete()
    
    # Új kapcsolatok létrehozása
    for server_admin_id in server_admin_ids:
        relation = ServerAdminAdmin(
            server_admin_id=server_admin_id,
            admin_id=user_id
        )
        db.add(relation)
    
    db.commit()
    
    request.session["success"] = f"{user.username} server admin kapcsolatai sikeresen frissítve!"
    return RedirectResponse(url="/admin/users", status_code=302)

@router.post("/admin/users/{user_id}/role")
async def update_user_role(
    request: Request,
    user_id: int,
    role: str = Form(...),
    db: Session = Depends(get_db)
):
    """Felhasználó rangjának módosítása"""
    current_user = require_manager_admin(request, db)
    
    # Felhasználó lekérése
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Felhasználó nem található")
    
    # Nem lehet saját magunkat módosítani
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Nem módosíthatod a saját rangodat")
    
    # Érvényes rang ellenőrzése
    valid_roles = ["user", "admin", "server_admin", "manager_admin"]
    if role not in valid_roles:
        raise HTTPException(status_code=400, detail="Érvénytelen rang")
    
    # Rang módosítás
    user.role = UserRole(role)
    db.commit()
    
    request.session["success"] = f"{user.username} rangja sikeresen frissítve {role}-re!"
    return RedirectResponse(url="/admin/users", status_code=302)

@router.post("/admin/users/delete")
async def delete_user(
    request: Request,
    user_id: int = Form(...),
    db: Session = Depends(get_db)
):
    """Felhasználó törlése"""
    current_user = require_manager_admin(request, db)
    
    # Felhasználó lekérése
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Felhasználó nem található")
    
    # Nem lehet saját magunkat törölni
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Nem törölheted a saját fiókodat")
    
    # Manager admin nem törölhető (biztonsági okokból)
    if user.role == UserRole.MANAGER_ADMIN:
        raise HTTPException(status_code=403, detail="Manager Admin felhasználó nem törölhető")
    
    # Kapcsolódó adatok törlése
    # ServerAdminAdmin kapcsolatok
    db.query(ServerAdminAdmin).filter(
        (ServerAdminAdmin.server_admin_id == user_id) | (ServerAdminAdmin.admin_id == user_id)
    ).delete()
    
    # Tokenek törlése
    db.query(Token).filter(Token.user_id == user_id).delete()
    
    # CartItem-ek törlése
    db.query(CartItem).filter(CartItem.user_id == user_id).delete()
    
    # Felhasználó törlése
    db.delete(user)
    db.commit()
    
    request.session["success"] = f"{user.username} felhasználó sikeresen törölve!"
    return RedirectResponse(url="/admin/users", status_code=302)


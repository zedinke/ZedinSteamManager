"""
Admin értesítési router
"""

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db, User
from app.services.notification_service import (
    create_notification,
    create_notification_for_users,
    create_notification_for_all_users
)
from app.services.email_service import send_notification_email

router = APIRouter()

def require_manager_admin(request: Request, db: Session) -> User:
    """Manager Admin jogosultság ellenőrzése"""
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=302, detail="Nincs bejelentkezve")
    
    current_user = db.query(User).filter(User.id == user_id).first()
    if not current_user or current_user.role.value != "manager_admin":
        raise HTTPException(status_code=403, detail="Nincs jogosultságod")
    return current_user

@router.get("/admin/notifications/create", response_class=HTMLResponse)
async def show_create_notification(
    request: Request,
    db: Session = Depends(get_db)
):
    """Értesítés írás oldal"""
    current_user = require_manager_admin(request, db)
    
    # Összes felhasználó lekérése
    from app.database import User
    users = db.query(User).order_by(User.username).all()
    
    from app.main import get_templates
    templates = get_templates()
    return templates.TemplateResponse(
        "admin/notifications_create.html",
        {"request": request, "users": users}
    )

@router.post("/admin/notifications/create")
async def create_notification_post(
    request: Request,
    title: str = Form(...),
    message: str = Form(...),
    notification_type: str = Form("admin_notification"),
    send_type: str = Form(...),  # "specific" vagy "all"
    user_ids: Optional[List[int]] = Form(None),
    send_email: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """Értesítés létrehozása"""
    current_user = require_manager_admin(request, db)
    
    if not title or not message:
        from app.main import get_templates
        templates = get_templates()
        from app.database import User
        users = db.query(User).order_by(User.username).all()
        return templates.TemplateResponse(
            "admin/notifications_create.html",
            {"request": request, "users": users, "error": "A cím és üzenet kötelező!"}
        )
    
    notifications = []
    users_to_email = []
    
    # send_email checkbox kezelése
    send_email_bool = send_email == "true" or send_email is True
    
    if send_type == "all":
        # Globális értesítés
        notifications = create_notification_for_all_users(db, notification_type, title, message)
        from app.database import User
        users_to_email = db.query(User).all()
    elif send_type == "specific":
        # Külön felhasználóknak
        # Form adatokból user_ids listát készítünk
        form_data = await request.form()
        user_ids_list = []
        for key, value in form_data.items():
            if key == "user_ids":
                try:
                    user_ids_list.append(int(value))
                except (ValueError, TypeError):
                    pass
        
        if not user_ids_list:
            from app.main import get_templates
            templates = get_templates()
            from app.database import User
            users = db.query(User).order_by(User.username).all()
            return templates.TemplateResponse(
                "admin/notifications_create.html",
                {"request": request, "users": users, "error": "Válassz legalább egy felhasználót!"}
            )
        
        notifications = create_notification_for_users(db, user_ids_list, notification_type, title, message)
        from app.database import User
        users_to_email = db.query(User).filter(User.id.in_(user_ids_list)).all()
    else:
        from app.main import get_templates
        templates = get_templates()
        from app.database import User
        users = db.query(User).order_by(User.username).all()
        return templates.TemplateResponse(
            "admin/notifications_create.html",
            {"request": request, "users": users, "error": "Válassz felhasználókat vagy válaszd a globális opciót!"}
        )
    
    # Email küldés ha kérték
    if send_email_bool and users_to_email:
        for user in users_to_email:
            try:
                await send_notification_email(user.email, user.username, title, message)
            except Exception as e:
                print(f"Email küldési hiba {user.email}-nak: {e}")
    
    success_msg = f"Értesítés sikeresen létrehozva {len(notifications)} felhasználónak"
    if send_email_bool:
        success_msg += " és email-ben elküldve"
    
    return RedirectResponse(url=f"/admin/notifications/create?success={success_msg}", status_code=302)


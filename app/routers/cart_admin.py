"""
Cart Admin router - Manager Admin kosár kezelés
"""

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db, User, CartItem, TokenType, Token, TokenExtensionRequest
from app.dependencies import require_manager_admin
from datetime import datetime, timedelta

router = APIRouter()

@router.get("/admin/carts", response_class=HTMLResponse)
async def list_all_carts(
    request: Request,
    db: Session = Depends(get_db)
):
    """Manager Admin: Összes kosár listázása felhasználóra lebontva"""
    current_user = require_manager_admin(request, db)
    
    # Összes Server Admin kosár elemeinek lekérése, felhasználóra csoportosítva
    cart_items = db.query(CartItem).join(
        User, CartItem.user_id == User.id
    ).filter(
        User.role == "server_admin"
    ).order_by(User.username, CartItem.created_at.desc()).all()
    
    # Felhasználóra csoportosítás
    carts_by_user = {}
    for item in cart_items:
        if item.user_id not in carts_by_user:
            carts_by_user[item.user_id] = {
                "user": item.user,
                "items": []
            }
        carts_by_user[item.user_id]["items"].append(item)
    
    from app.main import get_templates
    templates = get_templates()
    return templates.TemplateResponse(
        "admin/carts/list.html",
        {"request": request, "carts_by_user": carts_by_user}
    )

@router.post("/admin/carts/process/{item_id}")
async def process_cart_item(
    request: Request,
    item_id: int,
    action: str = Form(...),  # "approve" vagy "reject"
    notes: str = Form(None),
    db: Session = Depends(get_db)
):
    """Manager Admin: Kosár elem feldolgozása (jóváhagyás/elutasítás)"""
    current_user = require_manager_admin(request, db)
    
    cart_item = db.query(CartItem).filter(CartItem.id == item_id).first()
    if not cart_item:
        raise HTTPException(status_code=404, detail="Kosár elem nem található")
    
    if action == "approve":
        if cart_item.item_type == "token_request":
            # Token generálás
            from app.services.token_service import generate_token
            from app.config import settings
            
            generated_tokens = []
            for i in range(cart_item.quantity):
                token = generate_token(
                    db,
                    current_user.id,
                    cart_item.token_type,
                    settings.token_expiry_days
                )
                generated_tokens.append(token)
            
            # Tokenek hozzárendelése a felhasználóhoz
            for token in generated_tokens:
                token.user_id = cart_item.user_id
                token.is_active = True
                token.activated_at = datetime.now()
            
            db.commit()
            
            # Értesítés küldése
            from app.services.notification_service import create_notification
            create_notification(
                db,
                cart_item.user_id,
                "tokens_generated",
                f"{cart_item.quantity} token generálva",
                f"{cart_item.quantity} új token generálva és aktiválva lett számodra."
            )
            
        elif cart_item.item_type == "token_extension":
            # Token hosszabbítás
            token = db.query(Token).filter(Token.id == cart_item.token_id).first()
            if token:
                if token.expires_at and token.expires_at > datetime.now():
                    new_expires_at = token.expires_at + timedelta(days=cart_item.requested_days)
                else:
                    new_expires_at = datetime.now() + timedelta(days=cart_item.requested_days)
                
                token.expires_at = new_expires_at
                
                # Ha a token használatban van szerverrel, akkor frissítsük a szerver token_expires_at mezőjét is
                from app.database import ServerInstance
                servers = db.query(ServerInstance).filter(
                    ServerInstance.token_used_id == token.id
                ).all()
                
                for server in servers:
                    server.token_expires_at = new_expires_at
                    server.scheduled_deletion_date = new_expires_at + timedelta(days=30)
                
                db.commit()
                
                # Értesítés küldése
                from app.services.notification_service import create_notification
                create_notification(
                    db,
                    cart_item.user_id,
                    "token_extension_approved",
                    "Token hosszabbítás jóváhagyva",
                    f"A token hosszabbítási kérelmed jóváhagyásra került.\n\nHosszabbítás: {cart_item.requested_days} nap\nÚj lejárat: {new_expires_at.strftime('%Y-%m-%d %H:%M')}"
                )
        
        # Kosár elem törlése
        db.delete(cart_item)
        db.commit()
        
        return RedirectResponse(
            url="/admin/carts?success=Kosár+elem+jóváhagyva+és+feldolgozva",
            status_code=302
        )
    
    elif action == "reject":
        # Értesítés küldése
        from app.services.notification_service import create_notification
        rejection_message = "A kérelmed elutasításra került."
        if notes:
            rejection_message += f"\n\nMegjegyzés: {notes}"
        
        create_notification(
            db,
            cart_item.user_id,
            "cart_item_rejected",
            "Kérelem elutasítva",
            rejection_message
        )
        
        # Kosár elem törlése
        db.delete(cart_item)
        db.commit()
        
        return RedirectResponse(
            url="/admin/carts?success=Kosár+elem+elutasítva",
            status_code=302
        )
    
    raise HTTPException(status_code=400, detail="Érvénytelen művelet")


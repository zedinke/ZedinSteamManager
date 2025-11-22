"""
Token router
"""

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.database import get_db, User, TokenType, UserRole, TokenExtensionRequest, TokenRequest, CartItem
from app.services.token_service import generate_token, activate_token, send_token_to_user
from app.services.notification_service import create_notification
from app.database import Token, User, TokenExtensionRequest
from app.config import settings
from datetime import datetime, timedelta

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
    email_sent = False
    if generated_tokens:
        # Első token email-ben is
        email_sent = await send_token_to_user(db, generated_tokens[0], user_id)
        
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
        if email_sent:
            success_msg += f" Az első token email-ben is elküldve, a többi értesítésben."
        else:
            success_msg += f" Az első token email küldése sikertelen volt, de az értesítésben megtalálod."
    elif not email_sent:
        success_msg += f" Figyelmeztetés: Az email küldése sikertelen volt, de az értesítésben megtalálod a tokent."
    
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

@router.get("/tokens/requests", response_class=HTMLResponse)
async def list_token_requests(
    request: Request,
    db: Session = Depends(get_db)
):
    """Token igénylések listázása (Manager Admin)"""
    current_user = require_manager_admin(request, db)
    
    # Összes pending token igénylés lekérése
    token_requests = db.query(TokenRequest).join(
        User, TokenRequest.user_id == User.id
    ).filter(
        TokenRequest.status == "pending"
    ).order_by(TokenRequest.created_at.desc()).all()
    
    from app.main import get_templates
    templates = get_templates()
    return templates.TemplateResponse(
        "tokens/requests.html",
        {"request": request, "token_requests": token_requests}
    )

@router.post("/tokens/requests/{request_id}/process")
async def process_token_request(
    request: Request,
    request_id: int,
    action: str = Form(...),  # "approve" vagy "reject"
    notes: str = Form(None),
    db: Session = Depends(get_db)
):
    """Manager Admin: Token igénylés feldolgozása"""
    current_user = require_manager_admin(request, db)
    
    token_request = db.query(TokenRequest).filter(TokenRequest.id == request_id).first()
    if not token_request:
        raise HTTPException(status_code=404, detail="Token igénylés nem található")
    
    if action == "approve":
        # Token generálás
        generated_tokens = []
        for i in range(token_request.quantity):
            token = generate_token(
                db,
                current_user.id,
                token_request.token_type,
                token_request.expires_in_days or settings.token_expiry_days
            )
            generated_tokens.append(token)
        
        # Tokenek hozzárendelése a felhasználóhoz
        for token in generated_tokens:
            token.user_id = token_request.user_id
            token.is_active = True
            token.activated_at = datetime.now()
        
        db.commit()
        
        # Token igénylés státusz frissítése
        token_request.status = "approved"
        token_request.processed_at = datetime.now()
        token_request.processed_by_id = current_user.id
        db.commit()
        
        # Értesítés küldése
        create_notification(
            db,
            token_request.user_id,
            "token_request_approved",
            f"{token_request.quantity} token generálva",
            f"A token igénylésed jóváhagyásra került. {token_request.quantity} új token generálva és aktiválva lett számodra."
        )
        
        return RedirectResponse(
            url="/tokens/requests?success=Token+igénylés+jóváhagyva+és+feldolgozva",
            status_code=302
        )
    
    elif action == "reject":
        # Token igénylés elutasítása
        token_request.status = "rejected"
        token_request.processed_at = datetime.now()
        token_request.processed_by_id = current_user.id
        db.commit()
        
        # Értesítés küldése
        rejection_message = "A token igénylésed elutasításra került."
        if notes:
            rejection_message += f"\n\nMegjegyzés: {notes}"
        
        create_notification(
            db,
            token_request.user_id,
            "token_request_rejected",
            "Token igénylés elutasítva",
            rejection_message
        )
        
        return RedirectResponse(
            url="/tokens/requests?success=Token+igénylés+elutasítva",
            status_code=302
        )
    
    raise HTTPException(status_code=400, detail="Érvénytelen művelet")


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

@router.post("/tokens/extend")
async def extend_token(
    request: Request,
    token_id: int = Form(...),
    additional_days: int = Form(...),
    db: Session = Depends(get_db)
):
    """Token hosszabbítása (Manager Admin)"""
    current_user = require_manager_admin(request, db)
    
    if additional_days < 1 or additional_days > 365:
        raise HTTPException(status_code=400, detail="A hosszabbítás 1 és 365 nap között lehet")
    
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        raise HTTPException(status_code=404, detail="Token nem található")
    
    from datetime import datetime, timedelta
    
    # Ha a token már lejárt, akkor a mai dátumtól számolunk
    # Ha még nem járt le, akkor a jelenlegi lejárati dátumtól
    if token.expires_at and token.expires_at > datetime.now():
        new_expires_at = token.expires_at + timedelta(days=additional_days)
    else:
        new_expires_at = datetime.now() + timedelta(days=additional_days)
    
    token.expires_at = new_expires_at
    db.commit()
    
    # Ha a token használatban van szerverrel, akkor frissítsük a szerver token_expires_at mezőjét is
    from app.database import ServerInstance
    servers = db.query(ServerInstance).filter(
        ServerInstance.token_used_id == token.id
    ).all()
    
    for server in servers:
        server.token_expires_at = new_expires_at
        # Frissítsük a scheduled_deletion_date-et is (30 nap a token lejárata után)
        server.scheduled_deletion_date = new_expires_at + timedelta(days=30)
    
    db.commit()
    
    return RedirectResponse(
        url=f"/tokens/list?success=Token+hosszabbítva+{additional_days}+napra.+Új+lejárat:+{new_expires_at.strftime('%Y-%m-%d %H:%M')}",
        status_code=302
    )

@router.post("/tokens/request-extension")
async def request_token_extension(
    request: Request,
    token_id: int = Form(...),
    requested_days: int = Form(...),
    notes: str = Form(None),
    db: Session = Depends(get_db)
):
    """Server Admin: Token hosszabbítási kérés küldése"""
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    
    current_user = db.query(User).filter(User.id == user_id).first()
    if not current_user or current_user.role.value != "server_admin":
        raise HTTPException(status_code=403, detail="Nincs jogosultságod")
    
    if requested_days < 1 or requested_days > 365:
        raise HTTPException(status_code=400, detail="A hosszabbítás 1 és 365 nap között lehet")
    
    # Token ellenőrzése - csak a saját tokenjeit kérheti
    token = db.query(Token).filter(
        Token.id == token_id,
        Token.user_id == current_user.id
    ).first()
    
    if not token:
        raise HTTPException(status_code=404, detail="Token nem található vagy nincs hozzáférésed hozzá")
    
    # Ellenőrizzük, hogy van-e már ilyen elem a kosárban
    existing_cart_item = db.query(CartItem).filter(
        CartItem.user_id == current_user.id,
        CartItem.item_type == "token_extension",
        CartItem.token_id == token_id
    ).first()
    
    if existing_cart_item:
        return RedirectResponse(
            url="/dashboard?error=Már+van+ilyen+elem+a+kosárban",
            status_code=302
        )
    
    # Kosár elem létrehozása (a régi TokenExtensionRequest helyett)
    cart_item = CartItem(
        user_id=current_user.id,
        item_type="token_extension",
        token_id=token_id,
        requested_days=requested_days,
        notes=notes
    )
    
    db.add(cart_item)
    db.commit()
    
    return RedirectResponse(
        url="/dashboard?success=Hosszabbítási+kérés+hozzáadva+a+kosárhoz",
        status_code=302
    )

@router.post("/tokens/request")
async def request_token(
    request: Request,
    request_type: str = Form(...),  # "cart" vagy "free"
    token_type: str = Form(...),
    quantity: int = Form(...),
    expires_in_days: int = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db)
):
    """Server Admin: Token igénylés (kosárba vagy ingyenes)"""
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    
    current_user = db.query(User).filter(User.id == user_id).first()
    if not current_user or current_user.role.value != "server_admin":
        raise HTTPException(status_code=403, detail="Nincs jogosultságod")
    
    if token_type not in ["server_admin", "user"]:
        raise HTTPException(status_code=400, detail="Érvénytelen token típus")
    
    if quantity < 1 or quantity > 100:
        raise HTTPException(status_code=400, detail="A mennyiség 1 és 100 között lehet")
    
    if expires_in_days and (expires_in_days < 1 or expires_in_days > 365):
        raise HTTPException(status_code=400, detail="A lejárat 1 és 365 nap között lehet")
    
    token_type_enum = TokenType.SERVER_ADMIN if token_type == "server_admin" else TokenType.USER
    
    if request_type == "cart":
        # Kosárba helyezés
        cart_item = CartItem(
            user_id=current_user.id,
            item_type="token_request",
            token_type=token_type_enum,
            quantity=quantity,
            notes=notes
        )
        db.add(cart_item)
        db.commit()
        
        return RedirectResponse(
            url="/dashboard?success=Token+igénylés+hozzáadva+a+kosárhoz",
            status_code=302
        )
    
    elif request_type == "free":
        # Ingyenes igénylés manager admintól
        token_request = TokenRequest(
            user_id=current_user.id,
            token_type=token_type_enum,
            quantity=quantity,
            expires_in_days=expires_in_days,
            notes=notes,
            status="pending"
        )
        db.add(token_request)
        db.commit()
        
        # Értesítés küldése a manager adminoknak
        from app.database import UserRole
        manager_admins = db.query(User).filter(User.role == UserRole.MANAGER_ADMIN).all()
        for admin in manager_admins:
            create_notification(
                db,
                admin.id,
                "token_request",
                "Új token igénylés",
                f"{current_user.username} új token igénylést küldött.\nTípus: {token_type}\nMennyiség: {quantity}"
            )
        
        return RedirectResponse(
            url="/dashboard?success=Token+igénylés+elküldve+a+Manager+Adminisztrátornak",
            status_code=302
        )
    
    raise HTTPException(status_code=400, detail="Érvénytelen igénylés típus")


"""
Cart router - Server Admin kosár kezelés
"""

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db, User, CartItem, TokenType, Token
from datetime import datetime

router = APIRouter()

def require_server_admin(request: Request, db: Session = Depends(get_db)) -> User:
    """Server Admin jogosultság ellenőrzése"""
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=302, detail="Nincs bejelentkezve", headers={"Location": "/login"})
    
    current_user = db.query(User).filter(User.id == user_id).first()
    if not current_user or current_user.role.value != "server_admin":
        raise HTTPException(status_code=403, detail="Nincs jogosultságod - Server Admin szükséges")
    return current_user

@router.get("/cart", response_class=HTMLResponse)
async def show_cart(
    request: Request,
    db: Session = Depends(get_db)
):
    """Server Admin: Kosár megjelenítése"""
    current_user = require_server_admin(request, db)
    
    # Kosár elemek lekérése
    cart_items = db.query(CartItem).filter(
        CartItem.user_id == current_user.id
    ).order_by(CartItem.created_at.desc()).all()
    
    from app.main import get_templates
    templates = get_templates()
    return templates.TemplateResponse(
        "cart/index.html",
        {"request": request, "cart_items": cart_items}
    )

@router.post("/cart/add-token-request")
async def add_token_request(
    request: Request,
    token_type: str = Form(...),
    quantity: int = Form(...),
    notes: str = Form(None),
    db: Session = Depends(get_db)
):
    """Server Admin: Token igénylés hozzáadása a kosárhoz"""
    current_user = require_server_admin(request, db)
    
    if token_type not in ["server_admin", "user"]:
        raise HTTPException(status_code=400, detail="Érvénytelen token típus")
    
    if quantity < 1 or quantity > 100:
        raise HTTPException(status_code=400, detail="A mennyiség 1 és 100 között lehet")
    
    token_type_enum = TokenType.SERVER_ADMIN if token_type == "server_admin" else TokenType.USER
    
    # Kosár elem létrehozása
    cart_item = CartItem(
        user_id=current_user.id,
        item_type="token_request",
        token_type=token_type_enum,
        quantity=quantity,
        notes=notes
    )
    
    db.add(cart_item)
    db.commit()
    
    return RedirectResponse(url="/cart?success=Token+igénylés+hozzáadva+a+kosárhoz", status_code=302)

@router.post("/cart/add-extension-request")
async def add_extension_request(
    request: Request,
    token_id: int = Form(...),
    requested_days: int = Form(...),
    notes: str = Form(None),
    db: Session = Depends(get_db)
):
    """Server Admin: Token hosszabbítási kérés hozzáadása a kosárhoz"""
    current_user = require_server_admin(request, db)
    
    if requested_days < 1 or requested_days > 365:
        raise HTTPException(status_code=400, detail="A hosszabbítás 1 és 365 nap között lehet")
    
    # Token ellenőrzése - csak a saját tokenjeit kérheti
    token = db.query(Token).filter(
        Token.id == token_id,
        Token.user_id == current_user.id
    ).first()
    
    if not token:
        raise HTTPException(status_code=404, detail="Token nem található vagy nincs hozzáférésed hozzá")
    
    # Ellenőrizzük, hogy nincs-e már ilyen elem a kosárban
    existing = db.query(CartItem).filter(
        CartItem.user_id == current_user.id,
        CartItem.item_type == "token_extension",
        CartItem.token_id == token_id
    ).first()
    
    if existing:
        return RedirectResponse(url="/cart?error=Már+van+ilyen+elem+a+kosárban", status_code=302)
    
    # Kosár elem létrehozása
    cart_item = CartItem(
        user_id=current_user.id,
        item_type="token_extension",
        token_id=token_id,
        requested_days=requested_days,
        notes=notes
    )
    
    db.add(cart_item)
    db.commit()
    
    return RedirectResponse(url="/cart?success=Hosszabbítási+kérés+hozzáadva+a+kosárhoz", status_code=302)

@router.post("/cart/remove/{item_id}")
async def remove_cart_item(
    request: Request,
    item_id: int,
    db: Session = Depends(get_db)
):
    """Server Admin: Elem eltávolítása a kosárból"""
    current_user = require_server_admin(request, db)
    
    cart_item = db.query(CartItem).filter(
        CartItem.id == item_id,
        CartItem.user_id == current_user.id
    ).first()
    
    if not cart_item:
        raise HTTPException(status_code=404, detail="Kosár elem nem található")
    
    db.delete(cart_item)
    db.commit()
    
    return RedirectResponse(url="/cart?success=Elem+eltávolítva+a+kosárból", status_code=302)


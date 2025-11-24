"""
Cart router - Server Admin kosár kezelés
"""

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db, User, CartItem, TokenType, Token
from app.services.pricing_service import calculate_price
from datetime import datetime

router = APIRouter()

def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    """User vagy Server Admin jogosultság ellenőrzése"""
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=302, detail="Nincs bejelentkezve", headers={"Location": "/login"})
    
    current_user = db.query(User).filter(User.id == user_id).first()
    if not current_user or current_user.role.value not in ["user", "server_admin"]:
        raise HTTPException(status_code=403, detail="Nincs jogosultságod - Bejelentkezés szükséges")
    return current_user

@router.get("/cart", response_class=HTMLResponse)
async def show_cart(
    request: Request,
    db: Session = Depends(get_db)
):
    """User/Server Admin: Kosár megjelenítése"""
    current_user = require_user(request, db)
    
    # Kosár elemek lekérése
    cart_items = db.query(CartItem).filter(
        CartItem.user_id == current_user.id
    ).order_by(CartItem.created_at.desc()).all()
    
    # Árak számítása minden itemhez
    cart_items_with_pricing = []
    total_base_price = 0
    total_discount = 0
    total_final_price = 0
    
    for item in cart_items:
        try:
            if item.item_type == "token_request":
                # Token igénylés ár számítása
                # Period_months prioritásos, ha nincs, akkor expires_in_days (backward compatibility)
                pricing = calculate_price(
                    db,
                    item.token_type,
                    "token_request",
                    quantity=item.quantity,
                    period_months=item.period_months,
                    days=item.expires_in_days if not item.period_months else None
                )
                item.pricing = pricing
                total_base_price += pricing["total_base_price"]
                total_discount += pricing["discount_amount"]
                total_final_price += pricing["final_price"]
            elif item.item_type == "token_extension":
                # Token hosszabbítás ár számítása
                if item.token:
                    # Period_months prioritásos, ha nincs, akkor requested_days (backward compatibility)
                    pricing = calculate_price(
                        db,
                        item.token.token_type,
                        "token_extension",
                        quantity=1,
                        period_months=item.period_months,
                        days=item.requested_days if not item.period_months else None
                    )
                    item.pricing = pricing
                    total_base_price += pricing["total_base_price"]
                    total_discount += pricing["discount_amount"]
                    total_final_price += pricing["final_price"]
                else:
                    item.pricing = None
            elif item.item_type == "ram_upgrade":
                # RAM bővítés ár számítása
                import json
                try:
                    notes_data = json.loads(item.notes) if item.notes else {}
                    price_eur_cents = notes_data.get("price_eur_cents", 0)
                    pricing = {
                        "total_base_price": price_eur_cents,
                        "discount_amount": 0,
                        "final_price": price_eur_cents
                    }
                    item.pricing = pricing
                    item.ram_data = notes_data  # Kényelmi célokra
                    total_base_price += price_eur_cents
                    total_final_price += price_eur_cents
                except (json.JSONDecodeError, KeyError):
                    item.pricing = None
        except Exception as e:
            # Hiba esetén logoljuk, de ne akadjon el
            import logging
            logging.error(f"Error calculating price for cart item {item.id}: {e}")
            item.pricing = None
        
        cart_items_with_pricing.append(item)
    
    from app.main import get_templates
    templates = get_templates()
    return templates.TemplateResponse(
        "cart/index.html",
        {
            "request": request,
            "cart_items": cart_items_with_pricing,
            "total_base_price": total_base_price,
            "total_discount": total_discount,
            "total_final_price": total_final_price
        }
    )

@router.post("/cart/add-token-request")
async def add_token_request(
    request: Request,
    token_type: str = Form(...),
    quantity: int = Form(...),
    period_months: int = Form(...),
    notes: str = Form(None),
    db: Session = Depends(get_db)
):
    """User/Server Admin: Token igénylés hozzáadása a kosárhoz"""
    current_user = require_user(request, db)
    
    if token_type not in ["server_token"]:
        raise HTTPException(status_code=400, detail="Érvénytelen token típus")
    
    if quantity < 1 or quantity > 100:
        raise HTTPException(status_code=400, detail="A mennyiség 1 és 100 között lehet")
    
    # Periódus ellenőrzése
    from app.services.pricing_service import AVAILABLE_PERIODS
    if period_months not in AVAILABLE_PERIODS:
        raise HTTPException(status_code=400, detail="Érvénytelen periódus. Csak 1, 3, 6, vagy 12 hónap választható.")
    
    token_type_enum = TokenType.SERVER_TOKEN
    
    # Kosár elem létrehozása
    cart_item = CartItem(
        user_id=current_user.id,
        item_type="token_request",
        token_type=token_type_enum,
        quantity=quantity,
        period_months=period_months,
        notes=notes
    )
    
    db.add(cart_item)
    db.commit()
    
    return RedirectResponse(url="/cart?success=Token+igénylés+hozzáadva+a+kosárhoz", status_code=302)

@router.post("/cart/add-extension-request")
async def add_extension_request(
    request: Request,
    token_id: int = Form(...),
    period_months: int = Form(...),
    notes: str = Form(None),
    db: Session = Depends(get_db)
):
    """User/Server Admin: Token hosszabbítási kérés hozzáadása a kosárhoz"""
    current_user = require_user(request, db)
    
    # Periódus ellenőrzése
    from app.services.pricing_service import AVAILABLE_PERIODS
    if period_months not in AVAILABLE_PERIODS:
        raise HTTPException(status_code=400, detail="Érvénytelen periódus. Csak 1, 3, 6, vagy 12 hónap választható.")
    
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
        period_months=period_months,
        notes=notes
    )
    
    db.add(cart_item)
    db.commit()
    
    return RedirectResponse(url="/cart?success=Hosszabbítási+kérés+hozzáadva+a+kosárhoz", status_code=302)

@router.get("/cart/add-ram-upgrade")
async def add_ram_upgrade(
    request: Request,
    server_id: int,
    ram_gb: int,
    db: Session = Depends(get_db)
):
    """User/Server Admin: RAM bővítés hozzáadása a kosárhoz"""
    current_user = require_user(request, db)
    
    # Szerver ellenőrzése
    from app.database import ServerInstance
    server = db.query(ServerInstance).filter(
        ServerInstance.id == server_id,
        ServerInstance.server_admin_id == current_user.id
    ).first()
    
    if not server:
        raise HTTPException(status_code=404, detail="Szerver nem található")
    
    if ram_gb <= 0:
        raise HTTPException(status_code=400, detail="A RAM mennyiségnek pozitívnak kell lennie")
    
    # RAM árazás lekérése
    from app.database import RamPricing
    ram_pricing = db.query(RamPricing).order_by(RamPricing.updated_at.desc()).first()
    if not ram_pricing:
        raise HTTPException(status_code=400, detail="RAM árazás nincs beállítva. Kérjük, vedd fel a kapcsolatot a Manager Adminisztrátorral.")
    
    # Ár számítása
    price_eur_cents = ram_pricing.price_per_gb_eur * ram_gb
    
    # Kosár elem létrehozása (JSON-ben tároljuk a server_id-t és ram_gb-t)
    import json
    cart_item = CartItem(
        user_id=current_user.id,
        item_type="ram_upgrade",
        notes=json.dumps({
            "server_id": server_id,
            "server_name": server.name,
            "ram_gb": ram_gb,
            "price_eur_cents": price_eur_cents
        })
    )
    
    db.add(cart_item)
    db.commit()
    
    return RedirectResponse(url="/cart?success=RAM+bővítés+hozzáadva+a+kosárhoz", status_code=302)

@router.post("/cart/remove/{item_id}")
async def remove_cart_item(
    request: Request,
    item_id: int,
    db: Session = Depends(get_db)
):
    """User/Server Admin: Elem eltávolítása a kosárból"""
    current_user = require_user(request, db)
    
    cart_item = db.query(CartItem).filter(
        CartItem.id == item_id,
        CartItem.user_id == current_user.id
    ).first()
    
    if not cart_item:
        raise HTTPException(status_code=404, detail="Kosár elem nem található")
    
    db.delete(cart_item)
    db.commit()
    
    return RedirectResponse(url="/cart?success=Elem+eltávolítva+a+kosárból", status_code=302)


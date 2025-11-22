"""
Token árazás kezelő router - Manager Admin
"""

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db, User, TokenPricingRule, TokenBasePrice, TokenType
from app.dependencies import require_manager_admin
from datetime import datetime
from typing import Optional

router = APIRouter()

@router.get("/api/pricing/active-promotions")
async def get_active_promotions(
    db: Session = Depends(get_db)
):
    """Aktív promóciók lekérése (nyilvános API)"""
    now = datetime.now()
    
    # Csak az aktív, általános akciókat és időtartam kedvezményeket mutatjuk
    rules = db.query(TokenPricingRule).filter(
        TokenPricingRule.is_active == True,
        TokenPricingRule.rule_type.in_(["general_sale", "duration_discount"]),
        (TokenPricingRule.valid_from.is_(None)) | (TokenPricingRule.valid_from <= now),
        (TokenPricingRule.valid_until.is_(None)) | (TokenPricingRule.valid_until >= now)
    ).order_by(TokenPricingRule.priority.desc()).all()
    
    promotions = []
    for rule in rules:
        promo = {
            "name": rule.name,
            "type": rule.rule_type,
            "discount_percent": None,
            "min_duration_days": None,
            "notes": rule.notes
        }
        
        if rule.rule_type == "general_sale":
            promo["discount_percent"] = rule.discount_percent
        elif rule.rule_type == "duration_discount":
            promo["discount_percent"] = rule.duration_discount_percent
            promo["min_duration_days"] = rule.min_duration_days
        
        promotions.append(promo)
    
    return JSONResponse(content={"promotions": promotions})

@router.get("/admin/pricing", response_class=HTMLResponse)
async def pricing_management(
    request: Request,
    db: Session = Depends(get_db)
):
    """Manager Admin: Árazás kezelő oldal"""
    current_user = require_manager_admin(request, db)
    
    # Alapárak lekérése
    base_prices = db.query(TokenBasePrice).order_by(TokenBasePrice.token_type, TokenBasePrice.item_type).all()
    
    # Árazási szabályok lekérése
    pricing_rules = db.query(TokenPricingRule).order_by(
        TokenPricingRule.priority.desc(),
        TokenPricingRule.created_at.desc()
    ).all()
    
    from app.main import get_templates
    templates = get_templates()
    return templates.TemplateResponse(
        "admin/pricing/index.html",
        {
            "request": request,
            "base_prices": base_prices,
            "pricing_rules": pricing_rules
        }
    )

@router.post("/admin/pricing/base-price")
async def update_base_price(
    request: Request,
    token_type: str = Form(...),
    item_type: str = Form(...),
    base_price: int = Form(...),
    price_per_day: Optional[int] = Form(None),
    db: Session = Depends(get_db)
):
    """Alapár frissítése"""
    current_user = require_manager_admin(request, db)
    
    if token_type not in ["server_admin", "user"]:
        raise HTTPException(status_code=400, detail="Érvénytelen token típus")
    
    if item_type not in ["token_request", "token_extension"]:
        raise HTTPException(status_code=400, detail="Érvénytelen item típus")
    
    if base_price < 0:
        raise HTTPException(status_code=400, detail="Az ár nem lehet negatív")
    
    token_type_enum = TokenType.SERVER_ADMIN if token_type == "server_admin" else TokenType.USER
    
    # Meglévő ár keresése vagy új létrehozása
    base_price_obj = db.query(TokenBasePrice).filter(
        TokenBasePrice.token_type == token_type_enum,
        TokenBasePrice.item_type == item_type
    ).first()
    
    if base_price_obj:
        base_price_obj.base_price = base_price
        if price_per_day is not None:
            base_price_obj.price_per_day = price_per_day
        base_price_obj.updated_at = datetime.now()
    else:
        base_price_obj = TokenBasePrice(
            token_type=token_type_enum,
            item_type=item_type,
            base_price=base_price,
            price_per_day=price_per_day
        )
        db.add(base_price_obj)
    
    db.commit()
    
    return RedirectResponse(
        url="/admin/pricing?success=Alapár+frissítve",
        status_code=302
    )

@router.post("/admin/pricing/rule")
async def create_pricing_rule(
    request: Request,
    name: str = Form(...),
    rule_type: str = Form(...),
    is_active: bool = Form(False),
    discount_percent: Optional[int] = Form(None),
    min_quantity: Optional[int] = Form(None),
    quantity_discount_percent: Optional[int] = Form(None),
    min_duration_days: Optional[int] = Form(None),
    duration_discount_percent: Optional[int] = Form(None),
    applies_to_token_type: Optional[str] = Form(None),
    applies_to_item_type: Optional[str] = Form(None),
    valid_from: Optional[str] = Form(None),
    valid_until: Optional[str] = Form(None),
    priority: int = Form(0),
    notes: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """Árazási szabály létrehozása"""
    current_user = require_manager_admin(request, db)
    
    if rule_type not in ["general_sale", "quantity_discount", "duration_discount"]:
        raise HTTPException(status_code=400, detail="Érvénytelen szabály típus")
    
    # Validáció
    if rule_type == "general_sale" and not discount_percent:
        raise HTTPException(status_code=400, detail="Általános akcióhoz kedvezmény százalék szükséges")
    if rule_type == "quantity_discount" and (not min_quantity or not quantity_discount_percent):
        raise HTTPException(status_code=400, detail="Mennyiségi kedvezményhez minimum mennyiség és kedvezmény százalék szükséges")
    if rule_type == "duration_discount" and (not min_duration_days or not duration_discount_percent):
        raise HTTPException(status_code=400, detail="Időtartam kedvezményhez minimum napok és kedvezmény százalék szükséges")
    
    token_type_enum = None
    if applies_to_token_type:
        if applies_to_token_type not in ["server_admin", "user"]:
            raise HTTPException(status_code=400, detail="Érvénytelen token típus")
        token_type_enum = TokenType.SERVER_ADMIN if applies_to_token_type == "server_admin" else TokenType.USER
    
    valid_from_dt = None
    if valid_from:
        try:
            valid_from_dt = datetime.fromisoformat(valid_from.replace('Z', '+00:00'))
        except:
            raise HTTPException(status_code=400, detail="Érvénytelen valid_from dátum")
    
    valid_until_dt = None
    if valid_until:
        try:
            valid_until_dt = datetime.fromisoformat(valid_until.replace('Z', '+00:00'))
        except:
            raise HTTPException(status_code=400, detail="Érvénytelen valid_until dátum")
    
    rule = TokenPricingRule(
        name=name,
        rule_type=rule_type,
        is_active=is_active,
        discount_percent=discount_percent,
        min_quantity=min_quantity,
        quantity_discount_percent=quantity_discount_percent,
        min_duration_days=min_duration_days,
        duration_discount_percent=duration_discount_percent,
        applies_to_token_type=token_type_enum,
        applies_to_item_type=applies_to_item_type,
        valid_from=valid_from_dt,
        valid_until=valid_until_dt,
        priority=priority,
        notes=notes
    )
    
    db.add(rule)
    db.commit()
    
    return RedirectResponse(
        url="/admin/pricing?success=Árazási+szabály+létrehozva",
        status_code=302
    )

@router.post("/admin/pricing/rule/{rule_id}/toggle")
async def toggle_pricing_rule(
    request: Request,
    rule_id: int,
    db: Session = Depends(get_db)
):
    """Árazási szabály aktiválása/deaktiválása"""
    current_user = require_manager_admin(request, db)
    
    rule = db.query(TokenPricingRule).filter(TokenPricingRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Szabály nem található")
    
    rule.is_active = not rule.is_active
    db.commit()
    
    return RedirectResponse(
        url="/admin/pricing?success=Szabály+állapota+frissítve",
        status_code=302
    )

@router.post("/admin/pricing/rule/{rule_id}/delete")
async def delete_pricing_rule(
    request: Request,
    rule_id: int,
    db: Session = Depends(get_db)
):
    """Árazási szabály törlése"""
    current_user = require_manager_admin(request, db)
    
    rule = db.query(TokenPricingRule).filter(TokenPricingRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Szabály nem található")
    
    db.delete(rule)
    db.commit()
    
    return RedirectResponse(
        url="/admin/pricing?success=Szabály+törölve",
        status_code=302
    )


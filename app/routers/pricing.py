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

@router.get("/api/pricing/debug-rules")
async def debug_pricing_rules(
    token_type: str = "server_admin",
    item_type: str = "token_request",
    quantity: int = 1,
    days: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Debug endpoint az árazási szabályok ellenőrzéséhez"""
    from app.services.pricing_service import get_active_pricing_rules, calculate_price
    from app.database import TokenType
    
    token_type_enum = TokenType.SERVER_ADMIN if token_type == "server_admin" else TokenType.USER
    
    rules = get_active_pricing_rules(db, token_type_enum, item_type, quantity, days)
    pricing = calculate_price(db, token_type_enum, item_type, quantity, days)
    
    rules_data = []
    for rule in rules:
        rules_data.append({
            "id": rule.id,
            "name": rule.name,
            "type": rule.rule_type,
            "is_active": rule.is_active,
            "applies_to_token_type": rule.applies_to_token_type.value if rule.applies_to_token_type else None,
            "applies_to_item_type": rule.applies_to_item_type,
            "discount_percent": rule.discount_percent,
            "quantity_discount_percent": rule.quantity_discount_percent,
            "duration_discount_percent": rule.duration_discount_percent,
            "min_quantity": rule.min_quantity,
            "min_duration_days": rule.min_duration_days,
            "valid_from": rule.valid_from.isoformat() if rule.valid_from else None,
            "valid_until": rule.valid_until.isoformat() if rule.valid_until else None,
            "priority": rule.priority
        })
    
    return JSONResponse(content={
        "rules": rules_data,
        "pricing": pricing
    })

@router.get("/api/pricing/active-promotions")
async def get_active_promotions(
    db: Session = Depends(get_db)
):
    """Aktív promóciók lekérése (nyilvános API)"""
    now = datetime.now()
    
    # Csak az aktív, általános akciókat és időtartam kedvezményeket mutatjuk
    # (mennyiségi kedvezményeket nem, mert azok csak a kosárban relevánsak)
    all_rules = db.query(TokenPricingRule).filter(
        TokenPricingRule.is_active == True,
        TokenPricingRule.rule_type.in_(["general_sale", "duration_discount"])
    ).all()
    
    # Dátum ellenőrzés
    rules = []
    for rule in all_rules:
        # Ha van valid_from, akkor ellenőrizzük
        if rule.valid_from and rule.valid_from > now:
            continue
        # Ha van valid_until, akkor ellenőrizzük
        if rule.valid_until and rule.valid_until < now:
            continue
        rules.append(rule)
    
    # Prioritás szerint rendezés
    rules.sort(key=lambda x: x.priority, reverse=True)
    
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
    
    # Periódus árak lekérése
    from app.database import TokenPeriodPrice
    from app.services.pricing_service import AVAILABLE_PERIODS
    from app.services.exchange_rate_service import get_huf_eur_exchange_rate
    period_prices = db.query(TokenPeriodPrice).order_by(
        TokenPeriodPrice.token_type,
        TokenPeriodPrice.period_months
    ).all()
    
    # Exchange rate lekérése
    exchange_rate = get_huf_eur_exchange_rate() or 400.0
    
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
            "period_prices": period_prices,
            "available_periods": AVAILABLE_PERIODS,
            "exchange_rate": exchange_rate,
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

@router.post("/admin/pricing/period-price")
async def update_period_price(
    request: Request,
    token_type: str = Form(...),
    period_months: int = Form(...),
    price_eur: float = Form(...),  # EUR-ban (pl. 25.50)
    db: Session = Depends(get_db)
):
    """Periódus ár frissítése"""
    current_user = require_manager_admin(request, db)
    
    if token_type not in ["server_admin", "user"]:
        raise HTTPException(status_code=400, detail="Érvénytelen token típus")
    
    from app.services.pricing_service import AVAILABLE_PERIODS
    if period_months not in AVAILABLE_PERIODS:
        raise HTTPException(status_code=400, detail="Érvénytelen periódus. Csak 1, 3, 6, vagy 12 hónap választható.")
    
    if price_eur < 0:
        raise HTTPException(status_code=400, detail="Az ár nem lehet negatív")
    
    # EUR-ból centekbe konvertálás
    price_eur_cents = int(price_eur * 100)
    
    token_type_enum = TokenType.SERVER_ADMIN if token_type == "server_admin" else TokenType.USER
    
    # Meglévő ár keresése vagy új létrehozása
    period_price_obj = db.query(TokenPeriodPrice).filter(
        TokenPeriodPrice.token_type == token_type_enum,
        TokenPeriodPrice.period_months == period_months
    ).first()
    
    if period_price_obj:
        period_price_obj.price_eur = price_eur_cents
        period_price_obj.updated_at = datetime.now()
    else:
        period_price_obj = TokenPeriodPrice(
            token_type=token_type_enum,
            period_months=period_months,
            price_eur=price_eur_cents
        )
        db.add(period_price_obj)
    
    db.commit()
    
    return RedirectResponse(
        url="/admin/pricing?success=Periódus+ár+frissítve",
        status_code=302
    )

def parse_optional_int(value: Optional[str]) -> Optional[int]:
    """Üres string vagy None konvertálása None-ra, egyébként int-re"""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None

def parse_optional_datetime(value: Optional[str]) -> Optional[datetime]:
    """Üres string vagy None konvertálása None-ra, egyébként datetime-re"""
    if value is None or value == "":
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (ValueError, TypeError):
        return None

@router.post("/admin/pricing/rule")
async def create_pricing_rule(
    request: Request,
    name: str = Form(...),
    rule_type: str = Form(...),
    is_active: bool = Form(False),
    discount_percent: Optional[str] = Form(None),
    min_quantity: Optional[str] = Form(None),
    quantity_discount_percent: Optional[str] = Form(None),
    min_duration_days: Optional[str] = Form(None),
    duration_discount_percent: Optional[str] = Form(None),
    applies_to_token_type: Optional[str] = Form(None),
    applies_to_item_type: Optional[str] = Form(None),
    valid_from: Optional[str] = Form(None),
    valid_until: Optional[str] = Form(None),
    priority: str = Form("0"),
    notes: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """Árazási szabály létrehozása"""
    current_user = require_manager_admin(request, db)
    
    if rule_type not in ["general_sale", "quantity_discount", "duration_discount"]:
        raise HTTPException(status_code=400, detail="Érvénytelen szabály típus")
    
    # String értékek konvertálása
    discount_percent_int = parse_optional_int(discount_percent)
    min_quantity_int = parse_optional_int(min_quantity)
    quantity_discount_percent_int = parse_optional_int(quantity_discount_percent)
    min_duration_days_int = parse_optional_int(min_duration_days)
    duration_discount_percent_int = parse_optional_int(duration_discount_percent)
    priority_int = parse_optional_int(priority) or 0
    
    # Validáció
    if rule_type == "general_sale" and not discount_percent_int:
        raise HTTPException(status_code=400, detail="Általános akcióhoz kedvezmény százalék szükséges")
    if rule_type == "quantity_discount" and (not min_quantity_int or not quantity_discount_percent_int):
        raise HTTPException(status_code=400, detail="Mennyiségi kedvezményhez minimum mennyiség és kedvezmény százalék szükséges")
    if rule_type == "duration_discount" and (not min_duration_days_int or not duration_discount_percent_int):
        raise HTTPException(status_code=400, detail="Időtartam kedvezményhez minimum napok és kedvezmény százalék szükséges")
    
    token_type_enum = None
    if applies_to_token_type and applies_to_token_type != "":
        if applies_to_token_type not in ["server_admin", "user"]:
            raise HTTPException(status_code=400, detail="Érvénytelen token típus")
        token_type_enum = TokenType.SERVER_ADMIN if applies_to_token_type == "server_admin" else TokenType.USER
    
    valid_from_dt = parse_optional_datetime(valid_from)
    valid_until_dt = parse_optional_datetime(valid_until)
    
    # Üres string kezelése applies_to_item_type esetén
    applies_to_item_type_clean = None
    if applies_to_item_type and applies_to_item_type != "":
        applies_to_item_type_clean = applies_to_item_type
    
    rule = TokenPricingRule(
        name=name,
        rule_type=rule_type,
        is_active=is_active,
        discount_percent=discount_percent_int,
        min_quantity=min_quantity_int,
        quantity_discount_percent=quantity_discount_percent_int,
        min_duration_days=min_duration_days_int,
        duration_discount_percent=duration_discount_percent_int,
        applies_to_token_type=token_type_enum,
        applies_to_item_type=applies_to_item_type_clean,
        valid_from=valid_from_dt,
        valid_until=valid_until_dt,
        priority=priority_int,
        notes=notes if notes and notes != "" else None
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


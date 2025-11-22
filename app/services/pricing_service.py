"""
Token árazási szolgáltatás
"""

from sqlalchemy.orm import Session
from datetime import datetime
from app.database import TokenPricingRule, TokenBasePrice, TokenType
from typing import Optional, Dict, List

def get_base_price(db: Session, token_type: TokenType, item_type: str, days: Optional[int] = None) -> int:
    """Alapár lekérése"""
    base_price = db.query(TokenBasePrice).filter(
        TokenBasePrice.token_type == token_type,
        TokenBasePrice.item_type == item_type
    ).first()
    
    if not base_price:
        # Alapértelmezett árak, ha nincs beállítva
        if item_type == "token_request":
            default_prices = {
                TokenType.SERVER_ADMIN: 10000,  # 10,000 Ft
                TokenType.USER: 5000  # 5,000 Ft
            }
            return default_prices.get(token_type, 5000)
        else:  # token_extension
            return 1000  # 1,000 Ft/nap alapértelmezett
    
    if item_type == "token_extension" and days and base_price.price_per_day:
        return base_price.price_per_day * days
    
    return base_price.base_price

def get_active_pricing_rules(db: Session, token_type: TokenType, item_type: str, quantity: int = 1, days: Optional[int] = None) -> List[TokenPricingRule]:
    """Aktív árazási szabályok lekérése"""
    now = datetime.now()
    
    # Összes aktív szabály lekérése dátum szerint
    all_rules = db.query(TokenPricingRule).filter(
        TokenPricingRule.is_active == True
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
    
    # Szűrés a feltételek alapján
    applicable_rules = []
    token_type_value = token_type.value if hasattr(token_type, 'value') else str(token_type)
    
    for rule in rules:
        # Token típus ellenőrzés
        if rule.applies_to_token_type:
            # EnumType összehasonlítás - érték szerint
            rule_token_type_value = rule.applies_to_token_type.value if hasattr(rule.applies_to_token_type, 'value') else str(rule.applies_to_token_type)
            if rule_token_type_value != token_type_value:
                continue
        # Item típus ellenőrzés
        if rule.applies_to_item_type and rule.applies_to_item_type != item_type:
            continue
        
        if rule.rule_type == "general_sale":
            # Általános akció - mindig alkalmazható
            applicable_rules.append(rule)
        elif rule.rule_type == "quantity_discount":
            # Mennyiségi kedvezmény
            if rule.min_quantity and quantity >= rule.min_quantity:
                applicable_rules.append(rule)
        elif rule.rule_type == "duration_discount":
            # Időtartam kedvezmény
            if rule.min_duration_days and days and days >= rule.min_duration_days:
                applicable_rules.append(rule)
    
    # Prioritás szerint rendezés
    applicable_rules.sort(key=lambda x: x.priority, reverse=True)
    
    return applicable_rules

def calculate_price(
    db: Session,
    token_type: TokenType,
    item_type: str,
    quantity: int = 1,
    days: Optional[int] = None
) -> Dict:
    """Ár számítása kedvezményekkel"""
    base_price = get_base_price(db, token_type, item_type, days)
    total_base_price = base_price * quantity
    
    # Aktív szabályok lekérése
    rules = get_active_pricing_rules(db, token_type, item_type, quantity, days)
    
    # Kedvezmények alkalmazása (prioritás szerint - csak a legnagyobb kedvezményt alkalmazzuk)
    total_discount_percent = 0
    applied_rules = []
    best_rule = None
    
    for rule in rules:
        discount = 0
        if rule.rule_type == "general_sale" and rule.discount_percent:
            discount = rule.discount_percent
        elif rule.rule_type == "quantity_discount" and rule.quantity_discount_percent:
            discount = rule.quantity_discount_percent
        elif rule.rule_type == "duration_discount" and rule.duration_discount_percent:
            discount = rule.duration_discount_percent
        
        if discount > total_discount_percent:
            total_discount_percent = discount
            best_rule = rule
    
    # Csak a legjobb kedvezményt alkalmazzuk
    if best_rule:
        applied_rules.append({
            "name": best_rule.name,
            "type": best_rule.rule_type,
            "discount": total_discount_percent
        })
    
    # Végleges ár számítása
    discount_amount = int(total_base_price * total_discount_percent / 100)
    final_price = total_base_price - discount_amount
    
    return {
        "base_price": base_price,
        "quantity": quantity,
        "total_base_price": total_base_price,
        "discount_percent": total_discount_percent,
        "discount_amount": discount_amount,
        "final_price": max(0, final_price),  # Minimum 0
        "applied_rules": applied_rules
    }


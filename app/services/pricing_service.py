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
    
    rules = db.query(TokenPricingRule).filter(
        TokenPricingRule.is_active == True,
        (TokenPricingRule.valid_from.is_(None)) | (TokenPricingRule.valid_from <= now),
        (TokenPricingRule.valid_until.is_(None)) | (TokenPricingRule.valid_until >= now),
        (TokenPricingRule.applies_to_token_type.is_(None)) | (TokenPricingRule.applies_to_token_type == token_type),
        (TokenPricingRule.applies_to_item_type.is_(None)) | (TokenPricingRule.applies_to_item_type == item_type)
    ).order_by(TokenPricingRule.priority.desc()).all()
    
    # Szűrés a feltételek alapján
    applicable_rules = []
    for rule in rules:
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
    
    # Kedvezmények alkalmazása (prioritás szerint)
    total_discount_percent = 0
    applied_rules = []
    
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
            applied_rules.append({
                "name": rule.name,
                "type": rule.rule_type,
                "discount": discount
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


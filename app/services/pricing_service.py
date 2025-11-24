"""
Token árazási szolgáltatás
Az árak EUR-ban vannak tárolva (centekben)
"""

from sqlalchemy.orm import Session
from datetime import datetime
from app.database import TokenPricingRule, TokenBasePrice, TokenType, TokenPeriodPrice
from typing import Optional, Dict, List
from app.services.exchange_rate_service import get_huf_eur_exchange_rate, eur_to_huf

# Elérhető periódusok (hónapokban)
AVAILABLE_PERIODS = [1, 3, 6, 12]  # 1 hónap, 3 hónap, 6 hónap, 1 év

def period_months_to_days(period_months: int) -> int:
    """Periódus hónapokból napokká konvertálása"""
    period_days_map = {
        1: 30,   # 1 hónap = 30 nap
        3: 90,   # 3 hónap = 90 nap
        6: 180,  # 6 hónap = 180 nap
        12: 365  # 1 év = 365 nap
    }
    return period_days_map.get(period_months, 30)

def get_period_price(db: Session, token_type: TokenType, period_months: int) -> Optional[int]:
    """
    Periódus ár lekérése EUR centekben
    
    Args:
        db: Database session
        token_type: Token típus
        period_months: Periódus hónapokban (1, 3, 6, vagy 12)
    
    Returns:
        Ár EUR centekben vagy None ha nincs beállítva
    """
    if period_months not in AVAILABLE_PERIODS:
        return None
    
    period_price = db.query(TokenPeriodPrice).filter(
        TokenPeriodPrice.token_type == token_type,
        TokenPeriodPrice.period_months == period_months
    ).first()
    
    if period_price:
        return period_price.price_eur
    
    return None

def get_base_price(db: Session, token_type: TokenType, item_type: str, days: Optional[int] = None) -> int:
    """
    Alapár lekérése EUR centekben
    
    Returns:
        Ár EUR centekben (pl. 2500 = 25.00 EUR)
    """
    base_price = db.query(TokenBasePrice).filter(
        TokenBasePrice.token_type == token_type,
        TokenBasePrice.item_type == item_type
    ).first()
    
    if not base_price:
        # Alapértelmezett árak EUR-ban, ha nincs beállítva
        # Régi HUF árak konvertálása EUR-ra (400 HUF/EUR árfolyammal)
        exchange_rate = get_huf_eur_exchange_rate() or 400.0
        
        if item_type == "token_request":
            # Régi: 10,000 HUF és 5,000 HUF -> EUR-ban
            default_prices_huf = {
                TokenType.SERVER_TOKEN: 5000,  # 5,000 HUF (régi USER token ára)
                TokenType.USER: 5000  # Backward compatibility
            }
            # Konvertálás EUR-ra (centekben)
            huf_price = default_prices_huf.get(token_type, 5000)
            eur_price = huf_price / exchange_rate
            base = int(eur_price * 100)  # EUR centekben
            
            # Ha van napok száma megadva és van price_per_day, akkor számoljuk
            if days:
                # Alapértelmezett: 30 nap = base_price, tehát naponta base_price/30
                return int(base * days / 30)
            return base
        else:  # token_extension
            # Régi: 1,000 HUF/nap -> EUR-ban
            huf_per_day = 1000
            eur_per_day = huf_per_day / exchange_rate
            base_per_day = int(eur_per_day * 100)  # EUR centekben
            
            if days:
                return base_per_day * days
            return base_per_day
    
    # Ha van price_per_day és van napok száma, akkor használjuk azt
    if days and base_price.price_per_day:
        return base_price.price_per_day * days
    
    # Egyébként az alapár (token igénylésnél ez lehet fix ár vagy 30 napos ár)
    if item_type == "token_request" and days and not base_price.price_per_day:
        # Ha nincs price_per_day beállítva, de van napok száma, akkor arányosan számoljuk
        # Feltételezzük, hogy a base_price 30 napos ár
        return int(base_price.base_price * days / 30)
    
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
    days: Optional[int] = None,
    period_months: Optional[int] = None
) -> Dict:
    """
    Ár számítása kedvezményekkel
    
    Args:
        db: Database session
        token_type: Token típus
        item_type: "token_request" vagy "token_extension"
        quantity: Mennyiség
        days: Napok száma (deprecated, használd period_months helyette)
        period_months: Periódus hónapokban (1, 3, 6, vagy 12) - prioritásos
    
    Returns:
        Dict az ár információkkal
    """
    # Ha van period_months, akkor azt használjuk
    if period_months and period_months in AVAILABLE_PERIODS:
        period_price = get_period_price(db, token_type, period_months)
        if period_price:
            base_price = period_price
            # Napok számítása a periódusból (kedvezményekhez)
            days = period_months_to_days(period_months)
        else:
            # Ha nincs periódus ár, akkor a régi módszert használjuk
            base_price = get_base_price(db, token_type, item_type, days)
    else:
        # Régi módszer: napok alapján
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
    
    # Árfolyam lekérése HUF konverzióhoz
    exchange_rate = get_huf_eur_exchange_rate()
    
    return {
        "base_price": base_price,  # EUR centekben
        "quantity": quantity,
        "total_base_price": total_base_price,  # EUR centekben
        "discount_percent": total_discount_percent,
        "discount_amount": discount_amount,  # EUR centekben
        "final_price": max(0, final_price),  # EUR centekben, minimum 0
        "applied_rules": applied_rules,
        "exchange_rate": exchange_rate,  # HUF/EUR árfolyam
        # HUF értékek is (opcionális, ha szükséges)
        "base_price_huf": round(eur_to_huf(base_price / 100, exchange_rate), 2) if exchange_rate else None,
        "total_base_price_huf": round(eur_to_huf(total_base_price / 100, exchange_rate), 2) if exchange_rate else None,
        "discount_amount_huf": round(eur_to_huf(discount_amount / 100, exchange_rate), 2) if exchange_rate else None,
        "final_price_huf": round(eur_to_huf(final_price / 100, exchange_rate), 2) if exchange_rate else None,
    }


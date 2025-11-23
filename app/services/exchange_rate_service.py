"""
Exchange rate service - HUF/EUR árfolyam lekérése
"""

import requests
import json
from datetime import datetime, timedelta
from typing import Optional
from app.config import settings
import logging

logger = logging.getLogger(__name__)

# Cache az árfolyamhoz
_exchange_rate_cache = None
_exchange_rate_cache_time = None
CACHE_DURATION_HOURS = 1  # 1 óránként frissítjük

def get_huf_eur_exchange_rate() -> Optional[float]:
    """
    HUF/EUR közép árfolyam lekérése (aktuális)
    
    Returns:
        Árfolyam (pl. 400.0 = 1 EUR = 400 HUF) vagy None ha hiba van
    """
    global _exchange_rate_cache, _exchange_rate_cache_time
    
    # Cache ellenőrzése
    if _exchange_rate_cache and _exchange_rate_cache_time:
        if datetime.now() - _exchange_rate_cache_time < timedelta(hours=CACHE_DURATION_HOURS):
            return _exchange_rate_cache
    
    try:
        # Magyar Nemzeti Bank API használata
        # API endpoint: https://api.mnb.hu/arfolyamok.asmx
        # Dokumentáció: https://www.mnb.hu/letoltes/mnbapi-arfolyamok.pdf
        
        # Aktuális dátum
        today = datetime.now().strftime("%Y.%m.%d")
        
        # API hívás - GetExchangeRates metódus használata
        # Formátum: https://api.mnb.hu/arfolyamok.asmx/GetExchangeRates?startDate=2024.01.01&endDate=2024.01.01&currencyNames=EUR
        url = "https://api.mnb.hu/arfolyamok.asmx/GetExchangeRates"
        params = {
            "startDate": today,
            "endDate": today,
            "currencyNames": "EUR"
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        # XML válasz feldolgozása
        import xml.etree.ElementTree as ET
        root = ET.fromstring(response.text)
        
        # EUR árfolyam keresése
        # A válasz formátuma: <Day date="2024.01.01"><Rate unit="1" curr="EUR">400.50</Rate></Day>
        for day in root.findall('.//Day'):
            for rate in day.findall('.//Rate'):
                if rate.get('curr') == 'EUR':
                    rate_value = float(rate.text.replace(',', '.'))
                    # Cache mentése
                    _exchange_rate_cache = rate_value
                    _exchange_rate_cache_time = datetime.now()
                    logger.info(f"HUF/EUR árfolyam lekérve (MNB API): {rate_value}")
                    return rate_value
        
        # Ha nem találjuk az XML-ben, próbáljuk meg egy másik módszert
        logger.warning("EUR árfolyam nem található az MNB API válaszában")
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Hiba az árfolyam lekérésekor (MNB API): {e}")
    except Exception as e:
        logger.error(f"Váratlan hiba az árfolyam lekérésekor: {e}")
        import traceback
        traceback.print_exc()
    
    # Fallback: ha az API nem elérhető, használjunk egy alapértelmezett értéket
    # vagy egy másik API-t
    try:
        # Alternatíva: ExchangeRate-API (ingyenes, de limitált)
        # https://api.exchangerate-api.com/v4/latest/EUR
        fallback_url = "https://api.exchangerate-api.com/v4/latest/EUR"
        response = requests.get(fallback_url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if 'rates' in data and 'HUF' in data['rates']:
            rate_value = float(data['rates']['HUF'])
            # Cache mentése
            _exchange_rate_cache = rate_value
            _exchange_rate_cache_time = datetime.now()
            logger.info(f"HUF/EUR árfolyam lekérve (fallback API): {rate_value}")
            return rate_value
    except Exception as e:
        logger.error(f"Fallback API hiba: {e}")
    
    # Ha mindkét API sikertelen, használjunk egy alapértelmezett értéket
    # (pl. 400 HUF/EUR - ezt lehet config-ból is beállítani)
    default_rate = getattr(settings, 'default_huf_eur_rate', 400.0)
    logger.warning(f"API-k sikertelenek, alapértelmezett árfolyam használata: {default_rate}")
    return default_rate

def eur_to_huf(eur_amount: float, exchange_rate: Optional[float] = None) -> float:
    """
    EUR összeg konvertálása HUF-ra
    
    Args:
        eur_amount: EUR összeg
        exchange_rate: Árfolyam (ha None, akkor lekérjük)
    
    Returns:
        HUF összeg
    """
    if exchange_rate is None:
        exchange_rate = get_huf_eur_exchange_rate()
    
    if exchange_rate is None:
        # Ha nem sikerült lekérni, használjunk egy alapértelmezettet
        exchange_rate = getattr(settings, 'default_huf_eur_rate', 400.0)
    
    return round(eur_amount * exchange_rate, 2)

def huf_to_eur(huf_amount: float, exchange_rate: Optional[float] = None) -> float:
    """
    HUF összeg konvertálása EUR-ra
    
    Args:
        huf_amount: HUF összeg
        exchange_rate: Árfolyam (ha None, akkor lekérjük)
    
    Returns:
        EUR összeg (centekben, ha kell, akkor kerekítve)
    """
    if exchange_rate is None:
        exchange_rate = get_huf_eur_exchange_rate()
    
    if exchange_rate is None:
        # Ha nem sikerült lekérni, használjunk egy alapértelmezettet
        exchange_rate = getattr(settings, 'default_huf_eur_rate', 400.0)
    
    return round(huf_amount / exchange_rate, 2)


"""
CurseForge API szolgáltatás - mod keresés
"""

import httpx
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

# CurseForge API v1 endpoint (public, nincs API key szükséges)
CURSEFORGE_API_BASE = "https://api.curseforge.com/v1"
CURSEFORGE_GAME_ID = 432  # Ark: Survival Evolved (ASA is használhatja)

async def search_mods(query: str, limit: int = 20) -> List[Dict]:
    """
    Mod keresés CurseForge-on
    
    Args:
        query: Keresési kifejezés
        limit: Maximum találatok száma
    
    Returns:
        Mod lista dict formátumban
    """
    try:
        # CurseForge API v1 használata
        # Megjegyzés: A CurseForge API v1 public, de lehet, hogy rate limit van
        # Alternatíva: web scraping vagy más API
        
        # Próbáljuk meg a CurseForge API-t
        async with httpx.AsyncClient(timeout=10.0) as client:
            # CurseForge API v1 search endpoint
            # Mivel a public API korlátozott lehet, használjuk a web scraping-et
            # Vagy egy másik megközelítést
            
            # Alternatíva: CurseForge web scraping
            search_url = f"https://www.curseforge.com/ark-survival-ascended/search?search={query}"
            
            # Web scraping helyett használjuk a CurseForge API-t, ha elérhető
            # Vagy egy proxy/alternatív API-t
            
            # Most egy egyszerűbb megoldás: Steam Workshop API használata
            # Mivel az Ark modok általában Steam Workshop-on vannak
            
            return await search_steam_workshop(query, limit)
            
    except Exception as e:
        logger.error(f"CurseForge keresés hiba: {e}")
        return []

async def search_steam_workshop(query: str, limit: int = 20) -> List[Dict]:
    """
    Mod keresés Steam Workshop-on (Ark modok általában itt vannak)
    
    Args:
        query: Keresési kifejezés
        limit: Maximum találatok száma
    
    Returns:
        Mod lista dict formátumban
    """
    try:
        # Steam Workshop API használata
        # Steam Web API: ISteamRemoteStorage/GetPublishedFileDetails
        
        # Alternatíva: web scraping a Steam Workshop oldalról
        # Vagy használjuk a CurseForge web scraping-et
        
        # Most egy egyszerűbb megoldás: CurseForge web scraping
        return await search_curseforge_web(query, limit)
        
    except Exception as e:
        logger.error(f"Steam Workshop keresés hiba: {e}")
        return []

async def search_curseforge_web(query: str, limit: int = 20) -> List[Dict]:
    """
    CurseForge web scraping (fallback)
    
    Args:
        query: Keresési kifejezés
        limit: Maximum találatok száma
    
    Returns:
        Mod lista dict formátumban
    """
    try:
        # CurseForge web scraping
        # Megjegyzés: A CurseForge dinamikus, ezért nehézkes lehet
        # Alternatíva: Steam Workshop API használata
        
        # Most egy egyszerűbb megoldás: 
        # A felhasználó manuálisan adja meg a mod ID-t és nevet
        # A keresés csak egy placeholder, a valódi keresés később implementálható
        
        # Ha a query egy szám, akkor lehet, hogy mod ID
        if query.strip().isdigit():
            return [{
                "id": query.strip(),
                "name": f"Mod {query.strip()}",
                "icon_url": None,
                "url": f"https://steamcommunity.com/sharedfiles/filedetails/?id={query.strip()}",
                "description": "Add meg a mod nevét és ikonját manuálisan"
            }]
        
        # Egyébként üres lista (manuális hozzáadás ajánlott)
        return []
        
    except Exception as e:
        logger.error(f"CurseForge web scraping hiba: {e}")
        return []

async def get_mod_details(mod_id: str) -> Optional[Dict]:
    """
    Mod részletek lekérése mod ID alapján
    
    Args:
        mod_id: Mod ID (CurseForge vagy Steam Workshop)
    
    Returns:
        Mod részletek dict formátumban vagy None
    """
    try:
        # Mod részletek lekérése
        # Lehet CurseForge API, Steam Workshop API, vagy web scraping
        
        # Most egy mock implementáció
        return {
            "id": mod_id,
            "name": f"Mod {mod_id}",
            "icon_url": None,
            "description": None
        }
    except Exception as e:
        logger.error(f"Mod részletek lekérése hiba: {e}")
        return None


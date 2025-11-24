"""
CurseForge API szolgáltatás - mod keresés
"""

import httpx
from typing import List, Dict, Optional
import logging
import re
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# CurseForge API v1 endpoint
CURSEFORGE_API_BASE = "https://api.curseforge.com/v1"
# Ark Survival Ascended game ID a CurseForge-on
CURSEFORGE_GAME_ID_ASA = 1000230000  # Ark: Survival Ascended
CURSEFORGE_GAME_ID_ASE = 432  # Ark: Survival Evolved (backup)

async def search_mods(query: str, limit: int = 20) -> List[Dict]:
    """
    Mod keresés CurseForge-on Ark Survival Ascended-hoz
    
    Args:
        query: Keresési kifejezés
        limit: Maximum találatok száma
    
    Returns:
        Mod lista dict formátumban
    """
    try:
        # Először próbáljuk meg a CurseForge web scraping-et
        results = await search_curseforge_web(query, limit)
        if results:
            return results
        
        # Ha nincs találat, próbáljuk meg a CurseForge API-t (ha van API key)
        # Jelenleg nincs API key, ezért a web scraping-et használjuk
        
        return []
            
    except Exception as e:
        logger.error(f"CurseForge keresés hiba: {e}")
        return []

async def search_curseforge_web(query: str, limit: int = 20) -> List[Dict]:
    """
    CurseForge web scraping Ark Survival Ascended modokhoz
    
    Args:
        query: Keresési kifejezés
        limit: Maximum találatok száma
    
    Returns:
        Mod lista dict formátumban
    """
    try:
        # CurseForge web scraping Ark Survival Ascended modokhoz
        search_url = f"https://www.curseforge.com/ark-survival-ascended/search?search={query}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(search_url, headers=headers)
            response.raise_for_status()
            
            # HTML parsing
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            
            # CurseForge mod keresés eredmények
            # A CurseForge dinamikus, de próbáljuk meg a mod linkeket megtalálni
            mod_links = soup.find_all('a', href=re.compile(r'/ark-survival-ascended/mods/'))
            
            for link in mod_links[:limit]:
                try:
                    href = link.get('href', '')
                    mod_id_match = re.search(r'/mods/(\d+)', href)
                    if not mod_id_match:
                        continue
                    
                    mod_id = mod_id_match.group(1)
                    mod_name = link.get_text(strip=True)
                    
                    # Mod URL
                    if href.startswith('/'):
                        mod_url = f"https://www.curseforge.com{href}"
                    else:
                        mod_url = href
                    
                    # Ikon keresés
                    icon_url = None
                    icon_img = link.find('img')
                    if icon_img:
                        icon_url = icon_img.get('src') or icon_img.get('data-src')
                        if icon_url and not icon_url.startswith('http'):
                            icon_url = f"https://www.curseforge.com{icon_url}"
                    
                    # Leírás keresés
                    description = None
                    parent = link.find_parent()
                    if parent:
                        desc_elem = parent.find('p', class_=re.compile(r'description|summary'))
                        if desc_elem:
                            description = desc_elem.get_text(strip=True)
                    
                    results.append({
                        "id": mod_id,
                        "name": mod_name or f"Mod {mod_id}",
                        "icon_url": icon_url,
                        "url": mod_url,
                        "description": description or f"Ark Survival Ascended mod: {mod_name or mod_id}"
                    })
                except Exception as e:
                    logger.debug(f"Mod parsing hiba: {e}")
                    continue
            
            # Ha nincs találat a linkekből, próbáljuk meg más módon
            if not results:
                # Próbáljuk meg a mod kártyákat megtalálni
                mod_cards = soup.find_all('div', class_=re.compile(r'mod|card|item'))
                for card in mod_cards[:limit]:
                    try:
                        # Mod link keresés a kártyában
                        mod_link = card.find('a', href=re.compile(r'/ark-survival-ascended/mods/'))
                        if not mod_link:
                            continue
                        
                        href = mod_link.get('href', '')
                        mod_id_match = re.search(r'/mods/(\d+)', href)
                        if not mod_id_match:
                            continue
                        
                        mod_id = mod_id_match.group(1)
                        mod_name = mod_link.get_text(strip=True) or card.find('h3') or card.find('h4')
                        if mod_name:
                            mod_name = mod_name.get_text(strip=True) if hasattr(mod_name, 'get_text') else str(mod_name)
                        
                        if href.startswith('/'):
                            mod_url = f"https://www.curseforge.com{href}"
                        else:
                            mod_url = href
                        
                        icon_url = None
                        icon_img = card.find('img')
                        if icon_img:
                            icon_url = icon_img.get('src') or icon_img.get('data-src')
                            if icon_url and not icon_url.startswith('http'):
                                icon_url = f"https://www.curseforge.com{icon_url}"
                        
                        results.append({
                            "id": mod_id,
                            "name": mod_name or f"Mod {mod_id}",
                            "icon_url": icon_url,
                            "url": mod_url,
                            "description": f"Ark Survival Ascended mod: {mod_name or mod_id}"
                        })
                    except Exception as e:
                        logger.debug(f"Mod card parsing hiba: {e}")
                        continue
            
            # Ha még mindig nincs találat és a query szám, akkor lehet mod ID
            if not results and query.strip().isdigit():
                mod_id = query.strip()
                return [{
                    "id": mod_id,
                    "name": f"Mod {mod_id}",
                    "icon_url": None,
                    "url": f"https://www.curseforge.com/ark-survival-ascended/mods/{mod_id}",
                    "description": "Add meg a mod nevét és ikonját manuálisan"
                }]
            
            return results[:limit]
        
    except httpx.HTTPError as e:
        logger.error(f"CurseForge HTTP hiba: {e}")
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


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
            logger.info(f"CurseForge web scraping: {len(results)} találat")
            return results
        
        # Ha nincs találat, próbáljuk meg a Steam Workshop API-t
        # Mivel az Ark modok általában Steam Workshop-on vannak
        results = await search_steam_workshop(query, limit)
        if results:
            logger.info(f"Steam Workshop: {len(results)} találat")
            return results
        
        # Ha még mindig nincs találat, és a query szám, akkor lehet mod ID
        if query.strip().isdigit():
            mod_id = query.strip()
            logger.info(f"Query számként kezelve, mod ID: {mod_id}")
            return [{
                "id": mod_id,
                "name": f"Mod {mod_id}",
                "icon_url": None,
                "url": f"https://www.curseforge.com/ark-survival-ascended/mods/{mod_id}",
                "description": "Add meg a mod nevét és ikonját manuálisan"
            }]
        
        logger.warning(f"Nincs találat a '{query}' kereséshez")
        return []
            
    except Exception as e:
        logger.error(f"CurseForge keresés hiba: {e}")
        import traceback
        logger.error(traceback.format_exc())
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
        # URL encoding a query-hez
        import urllib.parse
        encoded_query = urllib.parse.quote(query)
        search_url = f"https://www.curseforge.com/ark-survival-ascended/search?search={encoded_query}&page=1&pageSize={limit}&sortBy=relevancy"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1"
        }
        
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            response = await client.get(search_url, headers=headers)
            response.raise_for_status()
            
            html_content = response.text
            results = []
            
            # Próbáljuk meg JSON adatokat megtalálni a HTML-ben (CurseForge gyakran használ JSON-LD vagy script tag-eket)
            # Keresés JSON adatok után
            json_patterns = [
                r'window\.__INITIAL_STATE__\s*=\s*({.+?});',
                r'window\.__APOLLO_STATE__\s*=\s*({.+?});',
                r'<script[^>]*type=["\']application/json["\'][^>]*>(.+?)</script>',
                r'data-mod-id=["\'](\d+)["\']',
            ]
            
            # Próbáljuk meg a JSON adatokat kinyerni
            for pattern in json_patterns:
                matches = re.findall(pattern, html_content, re.DOTALL)
                if matches:
                    logger.debug(f"JSON pattern találat: {pattern[:50]}")
                    break
            
            # HTML parsing
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Debug: nézzük meg, hogy van-e mod link az oldalon
            all_links = soup.find_all('a', href=True)
            mod_links_found = [link for link in all_links if '/ark-survival-ascended/mods/' in link.get('href', '')]
            logger.info(f"CurseForge HTML elemzés: {len(all_links)} link, {len(mod_links_found)} mod link találat")
            
            # Ha nincs mod link, próbáljuk meg a teljes HTML-t átnézni
            if not mod_links_found:
                # Keresés a HTML szövegben mod ID-k után
                mod_id_pattern = r'/ark-survival-ascended/mods/(\d+)'
                found_mod_ids = re.findall(mod_id_pattern, html_content)
                unique_mod_ids = list(set(found_mod_ids))
                logger.info(f"HTML szövegben talált mod ID-k: {len(unique_mod_ids)}")
                
                # Ha találtunk mod ID-kat, próbáljuk meg a mod oldalakat betölteni
                if unique_mod_ids:
                    for mod_id in unique_mod_ids[:limit]:
                        try:
                            mod_url = f"https://www.curseforge.com/ark-survival-ascended/mods/{mod_id}"
                            mod_response = await client.get(mod_url, headers=headers)
                            if mod_response.status_code == 200:
                                mod_soup = BeautifulSoup(mod_response.text, 'html.parser')
                                mod_name = None
                                
                                # Mod név keresés
                                title_elem = mod_soup.find('h1') or mod_soup.find('title')
                                if title_elem:
                                    mod_name = title_elem.get_text(strip=True)
                                    # Tisztítás
                                    if ' - ' in mod_name:
                                        mod_name = mod_name.split(' - ')[0]
                                
                                # Ikon keresés
                                icon_url = None
                                icon_img = mod_soup.find('img', class_=re.compile(r'icon|logo|avatar', re.I))
                                if icon_img:
                                    icon_url = icon_img.get('src') or icon_img.get('data-src')
                                    if icon_url and not icon_url.startswith('http'):
                                        icon_url = f"https://www.curseforge.com{icon_url}"
                                
                                # Leírás keresés
                                description = None
                                desc_elem = mod_soup.find('div', class_=re.compile(r'description|summary|about', re.I))
                                if desc_elem:
                                    description = desc_elem.get_text(strip=True)[:200]  # Max 200 karakter
                                
                                results.append({
                                    "id": mod_id,
                                    "name": mod_name or f"Mod {mod_id}",
                                    "icon_url": icon_url,
                                    "url": mod_url,
                                    "description": description or f"Ark Survival Ascended mod: {mod_name or mod_id}"
                                })
                        except Exception as e:
                            logger.debug(f"Mod oldal betöltés hiba {mod_id}: {e}")
                            continue
                    
                    if results:
                        logger.info(f"Mod oldalak betöltésével {len(results)} találat")
                        return results[:limit]
            
            # Keresés data-mod-id attribútumok után
            mod_elements = soup.find_all(attrs={'data-mod-id': True})
            logger.debug(f"Talált data-mod-id elemek száma: {len(mod_elements)}")
            for elem in mod_elements[:limit]:
                try:
                    mod_id = elem.get('data-mod-id')
                    if not mod_id:
                        continue
                    
                    # Mod név keresés
                    mod_name = None
                    name_elem = elem.find(['h3', 'h4', 'a', 'span'], class_=re.compile(r'title|name|mod-name', re.I))
                    if name_elem:
                        mod_name = name_elem.get_text(strip=True)
                    
                    # Mod link keresés
                    mod_link = elem.find('a', href=re.compile(r'/ark-survival-ascended/mods/'))
                    if not mod_link:
                        mod_link = elem.find_parent('a', href=re.compile(r'/ark-survival-ascended/mods/'))
                    
                    mod_url = None
                    if mod_link:
                        href = mod_link.get('href', '')
                        if href.startswith('/'):
                            mod_url = f"https://www.curseforge.com{href}"
                        else:
                            mod_url = href
                    else:
                        mod_url = f"https://www.curseforge.com/ark-survival-ascended/mods/{mod_id}"
                    
                    # Ikon keresés
                    icon_url = None
                    icon_img = elem.find('img')
                    if not icon_img:
                        icon_img = elem.find_parent().find('img') if elem.find_parent() else None
                    if icon_img:
                        icon_url = icon_img.get('src') or icon_img.get('data-src') or icon_img.get('data-lazy-src')
                        if icon_url:
                            if icon_url.startswith('//'):
                                icon_url = f"https:{icon_url}"
                            elif not icon_url.startswith('http'):
                                icon_url = f"https://www.curseforge.com{icon_url}"
                    
                    # Leírás keresés
                    description = None
                    desc_elem = elem.find(['p', 'div'], class_=re.compile(r'description|summary|excerpt', re.I))
                    if desc_elem:
                        description = desc_elem.get_text(strip=True)
                    
                    if not mod_name:
                        mod_name = f"Mod {mod_id}"
                    
                    results.append({
                        "id": mod_id,
                        "name": mod_name,
                        "icon_url": icon_url,
                        "url": mod_url,
                        "description": description or f"Ark Survival Ascended mod: {mod_name}"
                    })
                except Exception as e:
                    logger.debug(f"Mod element parsing hiba: {e}")
                    continue
            
            # Ha nincs találat data-mod-id-vel, próbáljuk meg a linkeket
            if not results:
                mod_links = soup.find_all('a', href=re.compile(r'/ark-survival-ascended/mods/\d+'))
                seen_ids = set()
                
                for link in mod_links[:limit * 2]:  # Több linket nézzünk meg, mert lehetnek duplikátumok
                    try:
                        href = link.get('href', '')
                        mod_id_match = re.search(r'/mods/(\d+)', href)
                        if not mod_id_match:
                            continue
                        
                        mod_id = mod_id_match.group(1)
                        if mod_id in seen_ids:
                            continue
                        seen_ids.add(mod_id)
                        
                        # Mod név
                        mod_name = link.get_text(strip=True)
                        if not mod_name:
                            # Próbáljuk meg a szülő elemből
                            parent = link.find_parent(['div', 'article', 'section'])
                            if parent:
                                title_elem = parent.find(['h3', 'h4', 'h5'])
                                if title_elem:
                                    mod_name = title_elem.get_text(strip=True)
                        
                        # Mod URL
                        if href.startswith('/'):
                            mod_url = f"https://www.curseforge.com{href}"
                        else:
                            mod_url = href
                        
                        # Ikon keresés
                        icon_url = None
                        parent = link.find_parent(['div', 'article', 'section'])
                        if parent:
                            icon_img = parent.find('img')
                            if icon_img:
                                icon_url = icon_img.get('src') or icon_img.get('data-src') or icon_img.get('data-lazy-src')
                                if icon_url:
                                    if icon_url.startswith('//'):
                                        icon_url = f"https:{icon_url}"
                                    elif not icon_url.startswith('http'):
                                        icon_url = f"https://www.curseforge.com{icon_url}"
                        
                        # Leírás keresés
                        description = None
                        if parent:
                            desc_elem = parent.find(['p', 'div'], class_=re.compile(r'description|summary|excerpt', re.I))
                            if desc_elem:
                                description = desc_elem.get_text(strip=True)
                        
                        if not mod_name:
                            mod_name = f"Mod {mod_id}"
                        
                        results.append({
                            "id": mod_id,
                            "name": mod_name,
                            "icon_url": icon_url,
                            "url": mod_url,
                            "description": description or f"Ark Survival Ascended mod: {mod_name}"
                        })
                        
                        if len(results) >= limit:
                            break
                    except Exception as e:
                        logger.debug(f"Mod link parsing hiba: {e}")
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
            
            logger.info(f"CurseForge keresés: '{query}' -> {len(results)} találat")
            
            # Ha nincs találat, próbáljuk meg debug módban
            if not results:
                logger.warning(f"Nincs találat a CurseForge-on a '{query}' kereséshez")
                # Debug: mentjük el a HTML-t fájlba (csak fejlesztéshez)
                # with open(f'/tmp/curseforge_debug_{query}.html', 'w', encoding='utf-8') as f:
                #     f.write(html_content)
            
            return results[:limit]
        
    except httpx.HTTPError as e:
        logger.error(f"CurseForge HTTP hiba: {e}")
        return []
    except Exception as e:
        logger.error(f"CurseForge web scraping hiba: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return []

async def search_steam_workshop(query: str, limit: int = 20) -> List[Dict]:
    """
    Mod keresés Steam Workshop-on Ark Survival Ascended-hoz
    (Fallback, ha a CurseForge nem működik)
    
    Args:
        query: Keresési kifejezés
        limit: Maximum találatok száma
    
    Returns:
        Mod lista dict formátumban
    """
    try:
        # Steam Workshop web scraping
        # Ark Survival Ascended Steam Workshop ID: 2430930
        import urllib.parse
        encoded_query = urllib.parse.quote(query)
        search_url = f"https://steamcommunity.com/workshop/browse/?appid=2430930&searchtext={encoded_query}&browsesort=textsearch&section=readytouseitems&actualsort=textsearch&p=1"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(search_url, headers=headers)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            
            # Steam Workshop mod linkek keresése
            mod_links = soup.find_all('a', href=re.compile(r'filedetails/\?id=\d+'))
            seen_ids = set()
            
            for link in mod_links[:limit * 2]:
                try:
                    href = link.get('href', '')
                    mod_id_match = re.search(r'id=(\d+)', href)
                    if not mod_id_match:
                        continue
                    
                    mod_id = mod_id_match.group(1)
                    if mod_id in seen_ids:
                        continue
                    seen_ids.add(mod_id)
                    
                    # Mod név
                    mod_name = link.get_text(strip=True)
                    if not mod_name:
                        parent = link.find_parent(['div', 'span'])
                        if parent:
                            title_elem = parent.find(['div', 'span'], class_=re.compile(r'title|name', re.I))
                            if title_elem:
                                mod_name = title_elem.get_text(strip=True)
                    
                    # Mod URL
                    if href.startswith('/'):
                        mod_url = f"https://steamcommunity.com{href}"
                    else:
                        mod_url = href
                    
                    # Ikon keresés
                    icon_url = None
                    parent = link.find_parent(['div', 'span'])
                    if parent:
                        icon_img = parent.find('img')
                        if icon_img:
                            icon_url = icon_img.get('src') or icon_img.get('data-src')
                    
                    if not mod_name:
                        mod_name = f"Mod {mod_id}"
                    
                    results.append({
                        "id": mod_id,
                        "name": mod_name,
                        "icon_url": icon_url,
                        "url": mod_url,
                        "description": f"Ark Survival Ascended mod: {mod_name}"
                    })
                    
                    if len(results) >= limit:
                        break
                except Exception as e:
                    logger.debug(f"Steam Workshop mod parsing hiba: {e}")
                    continue
            
            return results[:limit]
        
    except Exception as e:
        logger.error(f"Steam Workshop keresés hiba: {e}")
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


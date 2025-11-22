"""
AI Chat router - Magyar nyelvű AI csevegő
"""

from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse, HTMLResponse
from sqlalchemy.orm import Session
from app.database import get_db, User
from fastapi.templating import Jinja2Templates
from pathlib import Path
import httpx
import json
import os

router = APIRouter(prefix="/api/ai", tags=["ai_chat"])

# Template-ek inicializálása
BASE_DIR = Path(__file__).parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

def require_login(request: Request, db: Session = Depends(get_db)) -> User:
    """Bejelentkezés ellenőrzése"""
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Nincs bejelentkezve")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="Felhasználó nem található")
    return user

@router.post("/chat")
async def ai_chat(
    request: Request,
    message: dict,
    db: Session = Depends(get_db)
):
    """AI chat végpont"""
    current_user = require_login(request, db)
    
    user_message = message.get("message", "").strip()
    if not user_message:
        return JSONResponse(
            status_code=400,
            content={"error": "Üres üzenet"}
        )
    
    try:
        # OpenAI API használata (vagy más LLM API)
        # Ha nincs API key, akkor egy egyszerű válaszadó botot használunk
        openai_api_key = os.getenv("OPENAI_API_KEY")
        
        if openai_api_key:
            # OpenAI API használata
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {openai_api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "gpt-3.5-turbo",
                        "messages": [
                            {
                                "role": "system",
                                "content": """Te egy segítőkész magyar nyelvű AI asszisztens vagy a ZedinArkManager játék szerver kezelő rendszerben. 

A rendszer főbb funkciói:
- Szerverkezelés: Steam játék szerverek indítása és kezelése, SteamCMD telepítés
- Token rendszer: Token generálás, aktiválás, 1 token = 1 szerver indítás
- Felhasználókezelés: 4 szintű jogosultság (Manager Admin, Server Admin, Admin, User)
- Értesítések: In-app és email értesítések
- Ticket rendszer: Hibajelentés, beszélgetés Manager Admin-nal, értékelés
- Global Chat: Chat szobák játékokhoz, adminok közötti kommunikáció
- Dashboard: Statisztikák, szerver monitorozás (CPU, RAM, HDD, PING)

Válaszolj magyarul, barátságosan, részletesen és segítőkészen. Adj konkrét menüpontokat és lépéseket, amikor lehetséges."""
                            },
                            {
                                "role": "user",
                                "content": user_message
                            }
                        ],
                        "temperature": 0.7,
                        "max_tokens": 500
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    ai_response = data["choices"][0]["message"]["content"]
                    return JSONResponse({
                        "response": ai_response,
                        "success": True
                    })
                else:
                    # Ha hiba van az API-val, fallback botot használunk
                    return JSONResponse({
                        "response": get_fallback_response(user_message),
                        "success": True
                    })
        else:
            # Fallback bot, ha nincs API key
            return JSONResponse({
                "response": get_fallback_response(user_message),
                "success": True
            })
            
    except Exception as e:
        # Hiba esetén is fallback bot
        return JSONResponse({
            "response": get_fallback_response(user_message),
            "success": True
        })

def get_fallback_response(user_message: str) -> str:
    """Okos fallback válaszadó bot magyarul - részletes információk a manager-rel kapcsolatban"""
    message_lower = user_message.lower()
    
    # Üdvözlés
    if any(word in message_lower for word in ["szia", "helló", "üdv", "jó napot", "hello", "szervusz"]):
        return """Üdvözöllek! 😊 Én vagyok a ZedinArkManager AI asszisztensed.

A rendszer egy teljes körű játék szerver kezelő platform, amely a következő funkciókat kínálja:

🎮 **Szerverkezelés:**
- Steam játék szerverek indítása és kezelése
- SteamCMD automatikus telepítése és frissítése
- Szerver állapot monitorozás (CPU, RAM, HDD, PING)

🔑 **Token rendszer:**
- Token generálás és aktiválás
- 1 token = 1 szerver indítás jogosultság
- Token lejárat kezelés

👥 **Felhasználókezelés:**
- 4 szintű jogosultság rendszer (Manager Admin, Server Admin, Admin, User)
- Felhasználó létrehozás és kezelés
- Email verifikáció

📧 **Értesítések:**
- In-app és email értesítések
- Token aktiválás értesítések
- Globális értesítések küldése

🎫 **Ticket rendszer:**
- Hibajelentés és támogatás
- Beszélgetés a Manager Admin-nal
- Válasz értékelés

💬 **Global Chat:**
- Chat szobák játékokhoz
- Valós idejű kommunikáció
- Segítségkérés más adminoktól

Miben segíthetek neked? Kérdezz bátran!"""
    
    # Tokenek - részletesebb információ
    if any(word in message_lower for word in ["token", "tokenek", "aktiválás", "aktivál"]):
        return """🔑 **Token rendszer részletes információ:**

**Token típusok:**
- Server Admin token: Szerver Admin jogosultságot ad
- User token: Felhasználói jogosultságot ad

**Token használat:**
- 1 token = 1 szerver indítás jogosultság
- A tokeneket a Manager Admin generálja
- Token aktiválás: 'Tokenek > Token aktiválás' menüpont
- Token lejárat után automatikusan inaktívvá válik

**Tokenek kezelése:**
- Manager Admin: Token generálás, törlés, listázás
- Server Admin/User: Token aktiválás, saját tokenek megtekintése

**Fontos:**
- Minden szerver indítás 1 tokent használ fel
- Aktív tokenek száma a dashboard-on látható
- Ha nincs aktív token, nem lehet szervert indítani

Van még kérdésed a tokenekkel kapcsolatban?"""
    
    # Szerverek - részletesebb információ
    if any(word in message_lower for word in ["szerver", "server", "indítás", "indít", "játék", "steam"]):
        return """🎮 **Szerverkezelés részletes információ:**

**Szerver indítás:**
- Menüpont: 'Szerverkezelő > Szerver indítása'
- Szükséges: 1 aktív token
- Választható játékok: Manager Admin által engedélyezett játékok
- Port megadása opcionális

**Szerverek kezelése:**
- Saját szerverek listázása: 'Szerverkezelő > Szervereim'
- Szerver leállítása és törlése
- Szerver állapot monitorozás (Fut/Leállítva/Újraindítás)

**SteamCMD:**
- Automatikus telepítés: 'Szerverkezelés > SteamCMD'
- Frissítés és verzió ellenőrzés
- Telepítési útvonal: Server/SteamCMD

**Játékok hozzáadása:**
- Manager Admin: 'Szerverkezelés > Steam Szerverek'
- Játék neve, Steam App ID, leírás megadása
- Játékok aktiválása/deaktiválása

**Szerver állapotok:**
- 🟢 Fut: A szerver aktívan fut
- ⚪ Leállítva: A szerver nem fut
- 🟡 Újraindítás: A szerver újraindítás alatt

Van még kérdésed a szerverekkel kapcsolatban?"""
    
    # Jelszó és profil
    if any(word in message_lower for word in ["jelszó", "password", "változtatás", "profil", "beállítás"]):
        return """⚙️ **Profil és beállítások:**

**Jelszó változtatás:**
- Menüpont: 'Beállítások > Jelszó változtatás'
- Szükséges: Jelenlegi jelszó megadása
- Új jelszó minimum követelmények: biztonságos jelszó ajánlott

**Profil módosítás:**
- Menüpont: 'Beállítások > Profil módosítása'
- Módosítható: Felhasználónév, email
- Email változtatás után újra verifikáció szükséges

**Biztonsági tippek:**
- Használj erős, egyedi jelszót
- Ne oszd meg a jelszavadat senkivel
- Rendszeresen változtasd meg a jelszavadat

Van még kérdésed a beállításokkal kapcsolatban?"""
    
    # Ticket rendszer
    if any(word in message_lower for word in ["ticket", "hiba", "probléma", "segítség", "támogatás", "bug"]):
        return """🎫 **Ticket rendszer részletes információ:**

**Ticket nyitása:**
- Menüpont: 'Ticket rendszer > Új ticket'
- Több ticket egyidejűleg is nyitható
- Cím és részletes leírás megadása szükséges

**Ticket kezelés:**
- Ticketek listázása: 'Ticket rendszer > Ticketjeim'
- Beszélgetés a Manager Admin-nal a ticketben
- Ticket státuszok: Nyitott, Folyamatban, Megoldva, Zárva

**Ticket értékelés:**
- Megoldott ticket után értékelheted a Manager Admin válaszát
- 1-5 csillag értékelés + opcionális komment
- Csak egyszer értékelhetsz egy ticketet

**Ticket zárása:**
- A ticketet te is bezárhatod, ha megoldódott a probléma
- Manager Admin is bezárhatja a ticketet

**Hasznos tippek:**
- Adj minél részletesebb leírást a problémáról
- Válaszolj gyorsan a Manager Admin kérdéseire
- Értékeld a választ, hogy segíts a szolgáltatás fejlesztésében

Van még kérdésed a ticket rendszerrel kapcsolatban?"""
    
    # Chat rendszer
    if any(word in message_lower for word in ["chat", "beszélgetés", "szoba", "kommunikáció"]):
        return """💬 **Global Chat rendszer:**

**Chat szobák:**
- Automatikusan létrejön egy chat szoba minden új játékhoz
- Chat szobák listázása: 'Global Chat > Chat szobák'
- Valós idejű üzenetküldés

**Hozzáférések:**
- Manager Admin: Minden chat szobához hozzáférés
- Server Admin: Minden chat szobához hozzáférés
- Admin: Minden chat szobához hozzáférés
- User: Nincs hozzáférés

**Használat:**
- Segítségkérés más adminoktól
- Tapasztalatok megosztása
- Közös problémamegoldás

**Chat funkciók:**
- Üzenetküldés valós időben
- Üzenetek időbélyeggel
- Felhasználó név megjelenítés

Van még kérdésed a chat rendszerrel kapcsolatban?"""
    
    # Dashboard és statisztikák
    if any(word in message_lower for word in ["dashboard", "statisztika", "stat", "információ", "adatok"]):
        return """📊 **Dashboard és statisztikák:**

**Manager Admin dashboard:**
- Összes felhasználó száma
- Server Admin, Admin, User számok
- Aktív tokenek száma

**Server Admin dashboard:**
- Saját szerverek száma
- Admin felhasználók száma
- Aktív tokenjeim száma
- Tokenek listája

**Szerver monitorozás:**
- CPU kihasználtság (valós idejű grafikon)
- RAM használat (GB-ban)
- HDD használat (GB-ban)
- PING érték (ms)
- 2 másodperces frissítési időköz

**AI Asszisztens:**
- Jobb oldali chat widget
- Magyar nyelvű válaszok
- Rendszerrel kapcsolatos kérdések

Van még kérdésed a dashboard-dal kapcsolatban?"""
    
    # Jogosultságok és szerepkörök
    if any(word in message_lower for word in ["jogosultság", "szerepkör", "role", "rang", "admin", "user"]):
        return """👥 **Jogosultságok és szerepkörök:**

**Manager Admin:**
- Teljes hozzáférés a rendszerhez
- Token generálás és törlés
- Felhasználók kezelése
- Játékok hozzáadása
- SteamCMD telepítés
- Ticketek kezelése
- Git frissítés végrehajtása

**Server Admin:**
- Szerverek indítása (token szükséges)
- Admin felhasználók kezelése
- Saját szerverek kezelése
- Global Chat használata
- Ticketek nyitása

**Admin:**
- Szerverek kezelése (ha hozzá van rendelve)
- Global Chat használata
- Ticketek nyitása
- Profil módosítás

**User:**
- Token aktiválás
- Ticketek nyitása
- Profil módosítás
- Korlátozott hozzáférés

**Jogosultság emelés:**
- Token aktiválással lehet emelni
- Manager Admin hozza létre a tokeneket

Van még kérdésed a jogosultságokkal kapcsolatban?"""
    
    # Frissítés
    if any(word in message_lower for word in ["frissítés", "update", "git", "pull", "verzió"]):
        return """🔄 **Rendszer frissítés:**

**Automatikus frissítés:**
- Menüpont: 'Manager Frissítés' (csak Manager Admin)
- Git-ről automatikus frissítés
- Frissítések ellenőrzése
- Frissítés végrehajtása

**Frissítési folyamat:**
1. Git pull (új kód letöltése)
2. Függőségek frissítése (pip install)
3. Service újraindítása
4. Automatikus átirányítás az 'Updating' oldalra

**Frissítés közben:**
- A rendszer átmenetileg nem elérhető
- Felhasználók az 'Updating' oldalra kerülnek
- Automatikus vissza irányítás frissítés után

**Manuális frissítés:**
- Ha a webes felület nem működik
- Git pull + pip install + service restart

Van még kérdésed a frissítéssel kapcsolatban?"""
    
    # Általános segítség
    if any(word in message_lower for word in ["segítség", "help", "segít", "mit", "hogyan", "hogy"]):
        return """ℹ️ **Általános segítség:**

**Főbb funkciók:**
- 🎮 Szerverkezelés: Játék szerverek indítása és kezelése
- 🔑 Token rendszer: Jogosultság emelés tokenekkel
- 👥 Felhasználókezelés: Felhasználók létrehozása és kezelése
- 📧 Értesítések: In-app és email értesítések
- 🎫 Ticket rendszer: Hibajelentés és támogatás
- 💬 Global Chat: Adminok közötti kommunikáció
- 📊 Dashboard: Statisztikák és monitorozás

**Gyakori kérdések:**
- Token aktiválás: 'Tokenek > Token aktiválás'
- Szerver indítás: 'Szerverkezelő > Szerver indítása'
- Jelszó változtatás: 'Beállítások > Jelszó változtatás'
- Ticket nyitás: 'Ticket rendszer > Új ticket'

**Ha problémád van:**
- Nyiss egy ticketet a Manager Admin-nak
- Használd a Global Chat-ot más adminokkal
- Nézd meg a dashboard statisztikákat

Van konkrét kérdésed? Kérdezz bátran!"""
    
    # Köszönés
    if any(word in message_lower for word in ["kösz", "köszi", "köszi", "rendben", "oké", "ok", "kész"]):
        return "Szívesen! 😊 Ha még van kérdésed a ZedinArkManager rendszerrel kapcsolatban, nyugodtan kérdezz! Én itt vagyok, hogy segítsek! 🚀"
    
    # Alapértelmezett válasz - több információval
    return """Értem! 😊 

A ZedinArkManager egy teljes körű játék szerver kezelő platform. Főbb funkciók:

🎮 Szerverkezelés (Steam játék szerverek)
🔑 Token rendszer (jogosultság emelés)
👥 Felhasználókezelés (4 szintű jogosultság)
📧 Értesítések (in-app és email)
🎫 Ticket rendszer (hibajelentés)
💬 Global Chat (adminok közötti kommunikáció)
📊 Dashboard (statisztikák és monitorozás)

Kérdezz bátran konkrét funkciókról, például:
- "Hogyan aktiválok tokent?"
- "Hogyan indítok szervert?"
- "Mit csinál a Manager Admin?"
- "Hogyan nyitok ticketet?"

Vagy írj egy konkrét kérdést, és segítek!"""


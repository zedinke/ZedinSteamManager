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
                                "content": "Te egy segítőkész magyar nyelvű AI asszisztens vagy a ZedinArkManager játék szerver kezelő rendszerben. Válaszolj magyarul, barátságosan és segítőkészen."
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
    """Egyszerű fallback válaszadó bot magyarul"""
    message_lower = user_message.lower()
    
    # Üdvözlés
    if any(word in message_lower for word in ["szia", "helló", "üdv", "jó napot", "hello"]):
        return "Üdvözöllek! 😊 Miben segíthetek neked a ZedinArkManager rendszerben?"
    
    # Tokenek
    if any(word in message_lower for word in ["token", "tokenek", "aktiválás"]):
        return "A tokeneket a 'Token aktiválás' menüpontban tudod aktiválni. 1 token = 1 szerver indítása. Ha kérdésed van a tokenekkel kapcsolatban, kérlek, írj egy ticketet!"
    
    # Szerverek
    if any(word in message_lower for word in ["szerver", "server", "indítás", "indít"]):
        return "A szervereket a 'Szerverkezelő > Szerver indítása' menüpontban tudod indítani. Szükséges 1 aktív token minden szerver indításához."
    
    # Jelszó
    if any(word in message_lower for word in ["jelszó", "password", "változtatás"]):
        return "A jelszavadat a 'Beállítások > Jelszó változtatás' menüpontban tudod megváltoztatni."
    
    # Ticket
    if any(word in message_lower for word in ["ticket", "hiba", "probléma", "segítség"]):
        return "Ha problémád van vagy segítségre van szükséged, kérlek, nyiss egy ticketet a 'Ticket rendszer > Új ticket' menüpontban!"
    
    # Általános válaszok
    if "?" in user_message or any(word in message_lower for word in ["hogyan", "hogy", "mi", "mit"]):
        return "Kérlek, pontosítsd a kérdésedet! Segíthetek a tokenekkel, szerverekkel, jelszó változtatással és egyéb rendszerfunkciókkal kapcsolatban. Ha specifikus problémád van, nyiss egy ticketet!"
    
    # Köszönés
    if any(word in message_lower for word in ["kösz", "köszi", "köszi", "rendben", "oké", "ok"]):
        return "Szívesen! 😊 Ha még van kérdésed, nyugodtan kérdezz!"
    
    # Alapértelmezett válasz
    return "Értem! 😊 Ha segítségre van szükséged a rendszer használatában, kérlek, kérdezz bátran! Vagy nyiss egy ticketet, ha specifikus problémád van."


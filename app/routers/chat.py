"""
Chat router - Global chat rendszer
"""

from fastapi import APIRouter, Request, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.database import get_db, User, ChatRoom, ChatMessage
from fastapi.templating import Jinja2Templates
from pathlib import Path
from datetime import datetime, timedelta

router = APIRouter()

# Template-ek inicializálása
BASE_DIR = Path(__file__).parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

@router.get("/chat", response_class=HTMLResponse)
async def list_chat_rooms(request: Request, db: Session = Depends(get_db)):
    """Chat szobák listája"""
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    
    current_user = db.query(User).filter(User.id == user_id).first()
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)
    
    # Csak manager_admin, server_admin, admin
    if current_user.role.value not in ["manager_admin", "server_admin", "admin"]:
        raise HTTPException(status_code=403, detail="Nincs jogosultságod")
    
    rooms = db.query(ChatRoom).order_by(ChatRoom.created_at.desc()).all()
    
    # Utolsó üzenetek száma szobánként
    room_stats = {}
    for room in rooms:
        message_count = db.query(ChatMessage).filter(
            ChatMessage.room_id == room.id
        ).count()
        
        last_message = db.query(ChatMessage).filter(
            ChatMessage.room_id == room.id
        ).order_by(desc(ChatMessage.created_at)).first()
        
        room_stats[room.id] = {
            "message_count": message_count,
            "last_message": last_message
        }
    
    return templates.TemplateResponse(
        "chat/rooms.html",
        {
            "request": request,
            "rooms": rooms,
            "room_stats": room_stats,
            "user": current_user
        }
    )

@router.get("/chat/{room_id}", response_class=HTMLResponse)
async def view_chat_room(request: Request, room_id: int, db: Session = Depends(get_db)):
    """Chat szoba megtekintése"""
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    
    current_user = db.query(User).filter(User.id == user_id).first()
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)
    
    if current_user.role.value not in ["manager_admin", "server_admin", "admin"]:
        raise HTTPException(status_code=403, detail="Nincs jogosultságod")
    
    room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Chat szoba nem található")
    
    # Utolsó 100 üzenet
    messages = db.query(ChatMessage).filter(
        ChatMessage.room_id == room_id
    ).order_by(ChatMessage.created_at.desc()).limit(100).all()
    
    messages.reverse()  # Időrendi sorrend
    
    return templates.TemplateResponse(
        "chat/room.html",
        {
            "request": request,
            "room": room,
            "messages": messages,
            "user": current_user
        }
    )

@router.post("/chat/{room_id}/message")
async def send_message(
    request: Request,
    room_id: int,
    message: str = Form(...),
    db: Session = Depends(get_db)
):
    """Üzenet küldése"""
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    
    current_user = db.query(User).filter(User.id == user_id).first()
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)
    
    if current_user.role.value not in ["manager_admin", "server_admin", "admin"]:
        raise HTTPException(status_code=403, detail="Nincs jogosultságod")
    
    room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Chat szoba nem található")
    
    if not message.strip():
        request.session["error"] = "Az üzenet nem lehet üres!"
        return RedirectResponse(url=f"/chat/{room_id}", status_code=302)
    
    # Üzenet létrehozása
    chat_message = ChatMessage(
        room_id=room_id,
        user_id=current_user.id,
        message=message.strip()
    )
    db.add(chat_message)
    db.commit()
    
    return RedirectResponse(url=f"/chat/{room_id}", status_code=302)

@router.get("/api/chat/{room_id}/messages")
async def get_messages(
    request: Request,
    room_id: int,
    since: int = None,  # Timestamp
    db: Session = Depends(get_db)
):
    """API: Új üzenetek lekérése (polling)"""
    user_id = request.session.get("user_id")
    if not user_id:
        return JSONResponse(status_code=401, content={"error": "Nincs bejelentkezve"})
    
    current_user = db.query(User).filter(User.id == user_id).first()
    if not current_user:
        return JSONResponse(status_code=401, content={"error": "Nincs bejelentkezve"})
    
    if current_user.role.value not in ["manager_admin", "server_admin", "admin"]:
        return JSONResponse(status_code=403, content={"error": "Nincs jogosultságod"})
    
    room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
    if not room:
        return JSONResponse(status_code=404, content={"error": "Chat szoba nem található"})
    
    query = db.query(ChatMessage).filter(ChatMessage.room_id == room_id)
    
    if since:
        since_dt = datetime.fromtimestamp(since)
        query = query.filter(ChatMessage.created_at > since_dt)
    
    messages = query.order_by(ChatMessage.created_at).all()
    
    return JSONResponse(content={
        "messages": [
            {
                "id": msg.id,
                "user_id": msg.user_id,
                "username": msg.user.username,
                "message": msg.message,
                "created_at": msg.created_at.isoformat(),
                "timestamp": int(msg.created_at.timestamp())
            }
            for msg in messages
        ]
    })

@router.post("/admin/chat/create-room")
async def create_chat_room(
    request: Request,
    name: str = Form(...),
    game_name: str = Form(None),
    description: str = Form(None),
    db: Session = Depends(get_db)
):
    """Chat szoba létrehozása (Manager Admin)"""
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    
    current_user = db.query(User).filter(User.id == user_id).first()
    if not current_user or current_user.role.value != "manager_admin":
        raise HTTPException(status_code=403, detail="Nincs jogosultságod")
    
    # Ellenőrzés: létezik-e már ilyen név?
    existing = db.query(ChatRoom).filter(ChatRoom.name == name).first()
    if existing:
        request.session["error"] = "Már létezik ilyen nevű chat szoba!"
        return RedirectResponse(url="/chat", status_code=302)
    
    room = ChatRoom(
        name=name,
        game_name=game_name,
        description=description
    )
    db.add(room)
    db.commit()
    
    request.session["success"] = "Chat szoba sikeresen létrehozva!"
    return RedirectResponse(url="/chat", status_code=302)


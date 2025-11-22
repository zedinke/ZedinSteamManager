"""
Ticket router - hibajelentés rendszer
"""

from fastapi import APIRouter, Request, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.database import get_db, User, Ticket, TicketMessage, TicketRating, TicketStatus
from fastapi.templating import Jinja2Templates
from pathlib import Path

router = APIRouter()

# Template-ek inicializálása
BASE_DIR = Path(__file__).parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

@router.get("/tickets", response_class=HTMLResponse)
async def list_tickets(request: Request, db: Session = Depends(get_db)):
    """Felhasználó ticketjeinek listája"""
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    
    current_user = db.query(User).filter(User.id == user_id).first()
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)
    
    # Csak user, admin, server_admin
    if current_user.role.value not in ["user", "admin", "server_admin"]:
        raise HTTPException(status_code=403, detail="Nincs jogosultságod")
    
    user_tickets = db.query(Ticket).filter(
        Ticket.user_id == current_user.id
    ).order_by(desc(Ticket.created_at)).all()
    
    return templates.TemplateResponse(
        "tickets/list.html",
        {
            "request": request,
            "tickets": user_tickets,
            "user": current_user
        }
    )

@router.get("/tickets/create", response_class=HTMLResponse)
async def show_create_ticket(request: Request, db: Session = Depends(get_db)):
    """Új ticket létrehozása"""
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    
    current_user = db.query(User).filter(User.id == user_id).first()
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)
    
    if current_user.role.value not in ["user", "admin", "server_admin"]:
        raise HTTPException(status_code=403, detail="Nincs jogosultságod")
    
    return templates.TemplateResponse(
        "tickets/create.html",
        {"request": request, "user": current_user}
    )

@router.post("/tickets/create")
async def create_ticket(
    request: Request,
    title: str = Form(...),
    description: str = Form(...),
    db: Session = Depends(get_db)
):
    """Új ticket létrehozása"""
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    
    current_user = db.query(User).filter(User.id == user_id).first()
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)
    
    if current_user.role.value not in ["user", "admin", "server_admin"]:
        raise HTTPException(status_code=403, detail="Nincs jogosultságod")
    
    # Ticket létrehozása
    ticket = Ticket(
        user_id=current_user.id,
        title=title,
        description=description,
        status=TicketStatus.OPEN
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    
    # Első üzenet a leírásból
    first_message = TicketMessage(
        ticket_id=ticket.id,
        user_id=current_user.id,
        message=description
    )
    db.add(first_message)
    db.commit()
    
    request.session["success"] = "Ticket sikeresen létrehozva!"
    return RedirectResponse(url=f"/tickets/{ticket.id}", status_code=302)

@router.get("/tickets/{ticket_id}", response_class=HTMLResponse)
async def view_ticket(request: Request, ticket_id: int, db: Session = Depends(get_db)):
    """Ticket megtekintése"""
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    
    current_user = db.query(User).filter(User.id == user_id).first()
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)
    
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket nem található")
    
    # Csak a ticket tulajdonosa vagy manager admin láthatja
    if ticket.user_id != current_user.id and current_user.role.value != "manager_admin":
        raise HTTPException(status_code=403, detail="Nincs jogosultságod")
    
    messages = db.query(TicketMessage).filter(
        TicketMessage.ticket_id == ticket_id
    ).order_by(TicketMessage.created_at).all()
    
    rating = db.query(TicketRating).filter(
        TicketRating.ticket_id == ticket_id
    ).first()
    
    can_rate = (
        ticket.status.value in ["resolved", "closed"] and
        ticket.user_id == current_user.id and
        not rating
    )
    
    return templates.TemplateResponse(
        "tickets/view.html",
        {
            "request": request,
            "ticket": ticket,
            "messages": messages,
            "user": current_user,
            "rating": rating,
            "can_rate": can_rate
        }
    )

@router.post("/tickets/{ticket_id}/message")
async def add_message(
    request: Request,
    ticket_id: int,
    message: str = Form(...),
    db: Session = Depends(get_db)
):
    """Üzenet hozzáadása a tickethez"""
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    
    current_user = db.query(User).filter(User.id == user_id).first()
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)
    
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket nem található")
    
    # Csak a ticket tulajdonosa vagy manager admin írhat
    if ticket.user_id != current_user.id and current_user.role.value != "manager_admin":
        raise HTTPException(status_code=403, detail="Nincs jogosultságod")
    
    # Ha le van zárva, nem lehet üzenetet írni
    if ticket.status.value == "closed":
        request.session["error"] = "A lezárt tickethez nem lehet üzenetet írni!"
        return RedirectResponse(url=f"/tickets/{ticket_id}", status_code=302)
    
    # Üzenet hozzáadása
    ticket_message = TicketMessage(
        ticket_id=ticket_id,
        user_id=current_user.id,
        message=message
    )
    db.add(ticket_message)
    
    # Ha manager admin ír, akkor in_progress státusz
    if current_user.role.value == "manager_admin" and ticket.status.value == "open":
        ticket.status = TicketStatus.IN_PROGRESS
    
    db.commit()
    
    return RedirectResponse(url=f"/tickets/{ticket_id}", status_code=302)

@router.post("/tickets/{ticket_id}/rate")
async def rate_ticket(
    request: Request,
    ticket_id: int,
    rating: int = Form(...),
    comment: str = Form(None),
    db: Session = Depends(get_db)
):
    """Ticket értékelése"""
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    
    current_user = db.query(User).filter(User.id == user_id).first()
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)
    
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket nem található")
    
    # Csak a ticket tulajdonosa értékelheti
    if ticket.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Nincs jogosultságod")
    
    # Csak resolved vagy closed ticket értékelhető
    if ticket.status.value not in ["resolved", "closed"]:
        request.session["error"] = "Csak lezárt vagy megoldott ticket értékelhető!"
        return RedirectResponse(url=f"/tickets/{ticket_id}", status_code=302)
    
    # Ellenőrzés: már van értékelés?
    existing_rating = db.query(TicketRating).filter(
        TicketRating.ticket_id == ticket_id
    ).first()
    
    if existing_rating:
        request.session["error"] = "Ez a ticket már értékelve lett!"
        return RedirectResponse(url=f"/tickets/{ticket_id}", status_code=302)
    
    # Értékelés létrehozása
    ticket_rating = TicketRating(
        ticket_id=ticket_id,
        user_id=current_user.id,
        rating=rating,
        comment=comment
    )
    db.add(ticket_rating)
    db.commit()
    
    request.session["success"] = "Értékelés sikeresen elküldve!"
    return RedirectResponse(url=f"/tickets/{ticket_id}", status_code=302)

@router.post("/tickets/{ticket_id}/close")
async def close_ticket(
    request: Request,
    ticket_id: int,
    db: Session = Depends(get_db)
):
    """Ticket lezárása (csak a tulajdonos)"""
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    
    current_user = db.query(User).filter(User.id == user_id).first()
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)
    
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket nem található")
    
    # Csak a ticket tulajdonosa zárhatja le
    if ticket.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Nincs jogosultságod")
    
    if ticket.status.value == "closed":
        request.session["error"] = "A ticket már le van zárva!"
        return RedirectResponse(url=f"/tickets/{ticket_id}", status_code=302)
    
    from datetime import datetime
    ticket.status = TicketStatus.CLOSED
    ticket.closed_at = datetime.utcnow()
    ticket.closed_by_id = current_user.id
    db.commit()
    
    request.session["success"] = "Ticket sikeresen lezárva!"
    return RedirectResponse(url=f"/tickets/{ticket_id}", status_code=302)


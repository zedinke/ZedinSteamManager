"""
Ticket Admin router - Manager Admin ticket kezelés
"""

from fastapi import APIRouter, Request, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.database import get_db, User, Ticket, TicketMessage, TicketStatus
from app.dependencies import require_manager_admin
from fastapi.templating import Jinja2Templates
from pathlib import Path
from datetime import datetime

router = APIRouter()

# Template-ek inicializálása
BASE_DIR = Path(__file__).parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

@router.get("/admin/tickets", response_class=HTMLResponse)
async def list_all_tickets(request: Request, db: Session = Depends(get_db)):
    """Összes ticket listája (Manager Admin)"""
    current_user = require_manager_admin(request, db)
    
    status_filter = request.query_params.get("status", "all")
    
    query = db.query(Ticket)
    if status_filter != "all":
        query = query.filter(Ticket.status == TicketStatus(status_filter))
    
    tickets = query.order_by(desc(Ticket.created_at)).all()
    
    # Statisztikák
    stats = {
        "open": db.query(Ticket).filter(Ticket.status == TicketStatus.OPEN).count(),
        "in_progress": db.query(Ticket).filter(Ticket.status == TicketStatus.IN_PROGRESS).count(),
        "resolved": db.query(Ticket).filter(Ticket.status == TicketStatus.RESOLVED).count(),
        "closed": db.query(Ticket).filter(Ticket.status == TicketStatus.CLOSED).count(),
        "total": db.query(Ticket).count()
    }
    
    return templates.TemplateResponse(
        "admin/tickets/list.html",
        {
            "request": request,
            "tickets": tickets,
            "stats": stats,
            "status_filter": status_filter
        }
    )

@router.get("/admin/tickets/{ticket_id}", response_class=HTMLResponse)
async def view_ticket_admin(request: Request, ticket_id: int, db: Session = Depends(get_db)):
    """Ticket megtekintése (Manager Admin)"""
    current_user = require_manager_admin(request, db)
    
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket nem található")
    
    messages = db.query(TicketMessage).filter(
        TicketMessage.ticket_id == ticket_id
    ).order_by(TicketMessage.created_at).all()
    
    from app.database import TicketRating
    rating = db.query(TicketRating).filter(
        TicketRating.ticket_id == ticket_id
    ).first()
    
    return templates.TemplateResponse(
        "admin/tickets/view.html",
        {
            "request": request,
            "ticket": ticket,
            "messages": messages,
            "rating": rating
        }
    )

@router.post("/admin/tickets/{ticket_id}/message")
async def add_message_admin(
    request: Request,
    ticket_id: int,
    message: str = Form(...),
    db: Session = Depends(get_db)
):
    """Üzenet hozzáadása (Manager Admin)"""
    current_user = require_manager_admin(request, db)
    
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket nem található")
    
    if ticket.status.value == "closed":
        request.session["error"] = "A lezárt tickethez nem lehet üzenetet írni!"
        return RedirectResponse(url=f"/admin/tickets/{ticket_id}", status_code=302)
    
    # Üzenet hozzáadása
    ticket_message = TicketMessage(
        ticket_id=ticket_id,
        user_id=current_user.id,
        message=message
    )
    db.add(ticket_message)
    
    # Státusz frissítése
    if ticket.status.value == "open":
        ticket.status = TicketStatus.IN_PROGRESS
    
    db.commit()
    
    return RedirectResponse(url=f"/admin/tickets/{ticket_id}", status_code=302)

@router.post("/admin/tickets/{ticket_id}/status")
async def change_status(
    request: Request,
    ticket_id: int,
    status: str = Form(...),
    db: Session = Depends(get_db)
):
    """Ticket státusz változtatása (Manager Admin)"""
    current_user = require_manager_admin(request, db)
    
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket nem található")
    
    try:
        ticket.status = TicketStatus(status)
        
        if status == "closed":
            ticket.closed_at = datetime.utcnow()
            ticket.closed_by_id = current_user.id
        
        db.commit()
        request.session["success"] = "Ticket státusz sikeresen frissítve!"
    except ValueError:
        request.session["error"] = "Érvénytelen státusz!"
    
    return RedirectResponse(url=f"/admin/tickets/{ticket_id}", status_code=302)


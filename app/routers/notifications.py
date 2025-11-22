"""
Értesítési router
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db, User
from app.dependencies import require_login
from app.services.notification_service import (
    get_user_notifications,
    get_unread_count,
    mark_as_read,
    mark_all_as_read
)

router = APIRouter()

@router.get("/api/notifications")
async def get_notifications(
    request: Request,
    unread_only: bool = False,
    db: Session = Depends(get_db)
):
    """Értesítések API"""
    user_id = request.session.get("user_id")
    if not user_id:
        return JSONResponse({"notifications": [], "unread_count": 0})
    
    notifications = get_user_notifications(db, user_id, unread_only)
    unread_count = get_unread_count(db, user_id)
    
    return JSONResponse({
        "notifications": [
            {
                "id": n.id,
                "type": n.type,
                "title": n.title,
                "message": n.message,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat() if n.created_at else None
            }
            for n in notifications
        ],
        "unread_count": unread_count
    })

@router.post("/api/notifications/mark-read")
async def mark_notification_read(
    request: Request,
    notification_id: int = None,
    current_user: User = Depends(require_login),
    db: Session = Depends(get_db)
):
    """Értesítés olvasottnak jelölése"""
    # GET paraméterből vagy POST body-ből
    if not notification_id:
        try:
            body = await request.json()
            notification_id = body.get("notification_id")
        except:
            from fastapi import Query
            notification_id = request.query_params.get("notification_id")
    
    if not notification_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="notification_id szükséges")
    mark_as_read(db, int(notification_id), current_user.id)
    return JSONResponse({"success": True})

@router.post("/api/notifications/mark-all-read")
async def mark_all_notifications_read(
    request: Request,
    db: Session = Depends(get_db)
):
    """Összes értesítés olvasottnak jelölése"""
    user_id = request.session.get("user_id")
    if not user_id:
        return JSONResponse({"success": False, "error": "Not logged in"})
    
    count = mark_all_as_read(db, user_id)
    return JSONResponse({"success": True, "count": count})


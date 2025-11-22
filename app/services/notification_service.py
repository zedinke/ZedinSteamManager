"""
Értesítési szolgáltatás
"""

from sqlalchemy.orm import Session
from app.database import Notification

def create_notification(
    db: Session,
    user_id: int,
    notification_type: str,
    title: str,
    message: str
) -> Notification:
    """Értesítés létrehozása"""
    notification = Notification(
        user_id=user_id,
        type=notification_type,
        title=title,
        message=message
    )
    
    db.add(notification)
    db.commit()
    db.refresh(notification)
    
    return notification

def get_user_notifications(
    db: Session,
    user_id: int,
    unread_only: bool = False,
    limit: int = 50
) -> list[Notification]:
    """Felhasználó értesítései"""
    query = db.query(Notification).filter(Notification.user_id == user_id)
    
    if unread_only:
        query = query.filter(Notification.is_read == False)
    
    return query.order_by(Notification.created_at.desc()).limit(limit).all()

def get_unread_count(db: Session, user_id: int) -> int:
    """Olvasatlan értesítések száma"""
    return db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.is_read == False
    ).count()

def mark_as_read(db: Session, notification_id: int, user_id: int) -> bool:
    """Értesítés olvasottnak jelölése"""
    notification = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == user_id
    ).first()
    
    if notification:
        notification.is_read = True
        from datetime import datetime
        notification.read_at = datetime.utcnow()
        db.commit()
        return True
    
    return False

def mark_all_as_read(db: Session, user_id: int) -> int:
    """Összes értesítés olvasottnak jelölése"""
    from datetime import datetime
    count = db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.is_read == False
    ).update({
        Notification.is_read: True,
        Notification.read_at: datetime.utcnow()
    })
    
    db.commit()
    return count


"""Билдирүүлөр (🔔): жаңы сурануу, суранууга чечим, жаңы үй тапшырма ж.б."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mysite.db.database import get_db
from mysite.db.models import Notifications, Users
from mysite.security.permissions import get_current_user

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("")
def list_notifications(
    unread_only: bool = False,
    limit: int = 50,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Notifications).filter(Notifications.user_id == current_user.id)
    if unread_only:
        query = query.filter(Notifications.is_read.is_(False))

    items = query.order_by(Notifications.created_at.desc(), Notifications.id.desc()).limit(
        max(1, min(limit, 200))
    ).all()

    return [
        {
            "id": n.id,
            "title": n.title,
            "body": n.body,
            "link": n.link,
            "is_read": n.is_read,
            "created_at": n.created_at,
        }
        for n in items
    ]


@router.get("/unread-count")
def unread_count(
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    count = db.query(Notifications).filter(
        Notifications.user_id == current_user.id,
        Notifications.is_read.is_(False),
    ).count()
    return {"unread": count}


@router.post("/read-all")
def read_all(
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    updated = db.query(Notifications).filter(
        Notifications.user_id == current_user.id,
        Notifications.is_read.is_(False),
    ).update({"is_read": True})
    db.commit()
    return {"updated": updated}


@router.post("/{notification_id}/read")
def read_one(
    notification_id: int,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = db.query(Notifications).filter(
        Notifications.id == notification_id,
        Notifications.user_id == current_user.id,
    ).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Билдирүү табылган жок")
    item.is_read = True
    db.commit()
    return {"id": item.id, "is_read": True}

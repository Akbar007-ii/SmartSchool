"""Ачык портал (авторизациясыз): мектептердин визиттик карточкалары жана статистика."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from mysite.db.database import get_db
from mysite.db.models import Announcements, Classes, Schools, Users
from mysite.security.permissions import get_current_user
from mysite.db.models import OlympiadCandidates
from mysite.services.school import TEACHER_ROLES

router = APIRouter(tags=["Portal"])


def school_card(school: Schools) -> dict:
    return {
        "id": school.id,
        "name": school.name,
        "address": school.address,
        "phone": school.phone,
        "email": school.email,
        "logo_url": school.logo_url,
        "banner_url": school.banner_url,
        "director_name": school.director_name,
    }


def school_counts(db: Session, school_id: Optional[int] = None) -> dict:
    def count_users(roles):
        query = db.query(func.count(Users.id)).join(
            Schools, Schools.id == Users.school_id
        ).filter(
            Users.role.in_(roles),
            Users.is_active.is_(True),
            Schools.is_active.is_(True),
        )
        if school_id:
            query = query.filter(Users.school_id == school_id)
        return query.scalar() or 0

    return {
        "students": count_users(["STUDENT"]),
        "teachers": count_users(list(TEACHER_ROLES)),
    }


# Башкы бет: «12 мектеп · 25 000+ окуучу · 3 000+ мугалим»
@router.get("/public/stats")
def public_stats(db: Session = Depends(get_db)):
    schools = db.query(func.count(Schools.id)).filter(Schools.is_active.is_(True)).scalar() or 0
    return {"schools": schools, **school_counts(db)}


# «Мектеп тандоо» барагы
@router.get("/public/schools")
def public_schools(
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    query = db.query(Schools).filter(Schools.is_active.is_(True))
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        query = query.filter(Schools.name.ilike(pattern) | Schools.address.ilike(pattern))

    schools = query.order_by(Schools.name).offset(max(offset, 0)).limit(max(1, min(limit, 100))).all()
    return [school_card(s) for s in schools]


# Мектептин веб-баракчасы: карточка + статистика + акыркы жаңылыктар
@router.get("/public/schools/{school_id}")
def public_school(school_id: int, db: Session = Depends(get_db)):
    school = db.query(Schools).filter(
        Schools.id == school_id, Schools.is_active.is_(True)
    ).first()
    if school is None:
        raise HTTPException(status_code=404, detail="Мектеп табылган жок")

    news = (
        db.query(Announcements)
        .filter(Announcements.school_id == school.id)
        .order_by(Announcements.created_at.desc())
        .limit(5)
        .all()
    )

    return {
        **school_card(school),
        "stats": {
            **school_counts(db, school.id),
            "classes": db.query(func.count(Classes.id)).filter(Classes.school_id == school.id).scalar() or 0,
        },
        "news": [
            {
                "id": n.id,
                "title": n.title,
                "body": n.body,
                "image_url": n.image_url,
                "event_date": n.event_date,
                "created_at": n.created_at,
            }
            for n in news
        ],
    }


# Башкы панелдин жогорку карточкалары (окуучу / мугалим / класс / олимпиадага талапкер)
@router.get("/dashboard/stats")
def dashboard_stats(
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    school_id = current_user.school_id
    return {
        **school_counts(db, school_id),
        "classes": db.query(func.count(Classes.id)).filter(Classes.school_id == school_id).scalar() or 0,
        "olympiad_candidates": db.query(func.count(OlympiadCandidates.id)).filter(
            OlympiadCandidates.school_id == school_id,
            OlympiadCandidates.status == "SELECTED",
        ).scalar() or 0,
    }

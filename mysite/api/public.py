"""Ачык портал (авторизациясыз): мектептердин визиттик карточкалары жана статистика."""
from datetime import date, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from mysite.db.database import get_db
from mysite.db.models import Announcements, Classes, JournalEntries, Schools, Users
from mysite.security.permissions import get_current_user, require_roles
from mysite.db.models import OlympiadCandidates
from mysite.services.school import ADMIN_ROLES, TEACHER_ROLES
from mysite.services.timeutils import today_local

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


# Башкы панелдин графиги: мектептин үлгүрүүсү (орточо баа пайыз менен) жана катышуу.
# week — акыркы 7 күн, month — акыркы 30 күн (күн боюнча), year — акыркы 12 ай (ай боюнча).
@router.get("/dashboard/performance")
def dashboard_performance(
    period: Literal["week", "month", "year"] = "week",
    current_user: Users = Depends(require_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    today = today_local()
    if period == "year":
        month_index = today.year * 12 + today.month - 1 - 11
        date_from = date(month_index // 12, month_index % 12 + 1, 1)
    else:
        date_from = today - timedelta(days=(6 if period == "week" else 29))

    present = case((JournalEntries.attendance.in_(["Б", "К"]), 1), else_=0)
    rows = (
        db.query(
            JournalEntries.date,
            func.sum(JournalEntries.grade_value),
            func.count(JournalEntries.grade_value),
            func.sum(present),
            func.count(JournalEntries.attendance),
        )
        .filter(
            JournalEntries.school_id == current_user.school_id,
            JournalEntries.date >= date_from,
            JournalEntries.date <= today,
        )
        .group_by(JournalEntries.date)
        .all()
    )

    def bucket_key(day: date) -> date:
        return day.replace(day=1) if period == "year" else day

    totals = {}
    for day, grade_sum, grade_count, present_count, attendance_count in rows:
        bucket = totals.setdefault(bucket_key(day), [0, 0, 0, 0])
        bucket[0] += grade_sum or 0
        bucket[1] += grade_count or 0
        bucket[2] += present_count or 0
        bucket[3] += attendance_count or 0

    keys = []
    if period == "year":
        for offset in range(12):
            month_index = date_from.year * 12 + date_from.month - 1 + offset
            keys.append(date(month_index // 12, month_index % 12 + 1, 1))
    else:
        keys = [date_from + timedelta(days=offset) for offset in range((today - date_from).days + 1)]

    points = []
    for key in keys:
        grade_sum, grade_count, present_count, attendance_count = totals.get(key, [0, 0, 0, 0])
        average = round(grade_sum / grade_count, 2) if grade_count else None
        points.append({
            "date": key,
            "average": average,
            # 5 балл — 100%, 4 балл — 80%
            "percent": round(average / 5 * 100) if average is not None else None,
            "grades_count": grade_count,
            "attendance_percent": (
                round(present_count / attendance_count * 100) if attendance_count else None
            ),
        })

    return {"period": period, "points": points}

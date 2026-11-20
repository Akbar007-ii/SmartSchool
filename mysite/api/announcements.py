"""Жарыялар жана мектеп жаңылыктары."""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import or_
from sqlalchemy.orm import Session

from mysite.db.database import get_db
from mysite.db.models import Announcements, Users
from mysite.security.permissions import get_current_user, require_roles
from mysite.services.files import IMAGE_EXTENSIONS, delete_media, save_upload
from mysite.services.school import ADMIN_ROLES
from mysite.services.text_checks import check_form_texts

router = APIRouter(prefix="/announcements", tags=["Announcements"])

# Жарыянын аудиториясы. Класс жетекчи да мугалим катары эсептелет.
AUDIENCE_GROUPS = ("STUDENT", "PARENT", "TEACHER", "DEPUTY")
ROLE_TO_GROUP = {
    "STUDENT": "STUDENT",
    "PARENT": "PARENT",
    "TEACHER": "TEACHER",
    "CLASS_TEACHER": "TEACHER",
    "DEPUTY": "DEPUTY",
}


def parse_audience(value: Optional[str]) -> Optional[str]:
    """'STUDENT,PARENT' → текшерилген сап; 'ALL' же бош — None (баарына)."""
    if value is None or value.strip().upper() in ("", "ALL"):
        return None
    groups = {part.strip().upper() for part in value.split(",") if part.strip()}
    unknown = groups - set(AUDIENCE_GROUPS)
    if unknown:
        raise HTTPException(status_code=422, detail=f"Белгисиз аудитория: {', '.join(sorted(unknown))}")
    if groups == set(AUDIENCE_GROUPS):
        return None
    return ",".join(group for group in AUDIENCE_GROUPS if group in groups)


def visible_to(query, user: Users):
    """Директор жана завуч баарын көрөт (жарыяларды башкарышат), калгандар — өздөрүнө тиешелүүсүн."""
    if user.role in ADMIN_ROLES:
        return query
    group = ROLE_TO_GROUP.get(user.role)
    if group is None:
        return query.filter(Announcements.audience.is_(None))
    return query.filter(or_(
        Announcements.audience.is_(None),
        Announcements.audience.like(f"%{group}%"),
    ))


def serialize(a: Announcements) -> dict:
    return {
        "id": a.id,
        "school_id": a.school_id,
        "title": a.title,
        "body": a.body,
        "image_url": a.image_url,
        "event_date": a.event_date,
        "audience": a.audience.split(",") if a.audience else None,
        "created_by": a.created_by,
        "created_at": a.created_at,
    }


def get_or_404(db: Session, announcement_id: int, school_id: int) -> Announcements:
    item = db.query(Announcements).filter(
        Announcements.id == announcement_id,
        Announcements.school_id == school_id,
    ).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Жарыя табылган жок")
    return item


@router.get("")
def list_announcements(
    limit: int = 20,
    offset: int = 0,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    limit = max(1, min(limit, 100))
    query = db.query(Announcements).filter(Announcements.school_id == current_user.school_id)
    items = (
        visible_to(query, current_user)
        .order_by(Announcements.created_at.desc())
        .offset(max(offset, 0))
        .limit(limit)
        .all()
    )
    return [serialize(a) for a in items]


@router.get("/{announcement_id}")
def get_announcement(
    announcement_id: int,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = get_or_404(db, announcement_id, current_user.school_id)
    if visible_to(db.query(Announcements).filter(Announcements.id == item.id), current_user).first() is None:
        raise HTTPException(status_code=404, detail="Жарыя табылган жок")
    return serialize(item)


@router.post("", status_code=201)
def create_announcement(
    title: str = Form(..., min_length=2, max_length=200),
    body: Optional[str] = Form(default=None),
    event_date: Optional[date] = Form(default=None),
    audience: Optional[str] = Form(default=None),
    image: Optional[UploadFile] = File(default=None),
    current_user: Users = Depends(require_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    check_form_texts(title=title, body=body)
    audience_value = parse_audience(audience)
    image_url = None
    if image is not None and image.filename:
        image_url = save_upload(
            image, f"announcements/{current_user.school_id}", allowed=IMAGE_EXTENSIONS
        )

    item = Announcements(
        school_id=current_user.school_id,
        title=title.strip(),
        body=body,
        image_url=image_url,
        event_date=event_date,
        audience=audience_value,
        created_by=current_user.id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return serialize(item)


@router.put("/{announcement_id}")
def update_announcement(
    announcement_id: int,
    title: Optional[str] = Form(default=None, min_length=2, max_length=200),
    body: Optional[str] = Form(default=None),
    event_date: Optional[date] = Form(default=None),
    # Берилбесе — өзгөрбөйт; "ALL" — баарына.
    audience: Optional[str] = Form(default=None),
    image: Optional[UploadFile] = File(default=None),
    current_user: Users = Depends(require_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    check_form_texts(title=title, body=body)
    item = get_or_404(db, announcement_id, current_user.school_id)
    if audience is not None:
        item.audience = parse_audience(audience)

    if title is not None:
        item.title = title.strip()
    if body is not None:
        item.body = body
    if event_date is not None:
        item.event_date = event_date

    old_image = None
    if image is not None and image.filename:
        old_image = item.image_url
        item.image_url = save_upload(
            image, f"announcements/{current_user.school_id}", allowed=IMAGE_EXTENSIONS
        )

    db.commit()
    delete_media(old_image)
    db.refresh(item)
    return serialize(item)


@router.delete("/{announcement_id}")
def delete_announcement(
    announcement_id: int,
    current_user: Users = Depends(require_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    item = get_or_404(db, announcement_id, current_user.school_id)
    image_url = item.image_url
    db.delete(item)
    db.commit()
    delete_media(image_url)
    return {"message": "Жарыя өчүрүлдү"}

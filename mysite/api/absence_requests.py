"""Сабактан сурануу модулу (ТЗ 5-бөлүм, оңдолгон RBAC менен).

ӨЗГӨРТҮҮ (ТЗга карата): сурануу жиберүүгө АТА-ЭНЕГЕ ГАНА уруксат берилет.
Окуучу сурануу жибере албайт жана бул модулга кире албайт.

Эрежелер:
  * Бүгүнкү күнгө сурануу Бишкек убактысы менен 08:00гө чейин гана кабыл алынат
    (08:00:00дөн баштап сервер баш тартат). Келерки күндөргө алдын ала жиберсе болот.
  * Класс жетекчи өз классынын суранууларын «Уруксат берүү» же «Четке кагуу» кылат.
  * Уруксат берилгенде ошол күнкү ошол класстын бардык сабактарына «С» коюлат.
  * Директор/Завуч бардык суранууларды көрөт (көзөмөл), бирок чечим чыгарбайт.
"""
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from mysite.db.database import get_db
from mysite.db.models import (
    AbsenceRequests,
    Classes,
    JournalEntries,
    ParentStudents,
    TeacherAssignments,
    Users,
)
from mysite.db.schema import AbsenceRequestCreate, AbsenceReview
from mysite.security.permissions import get_current_user, require_roles
from mysite.services.notifications import notify
from mysite.services.rating import recompute_subject_xp, sync_badges
from mysite.services.school import (
    ADMIN_ROLES,
    TEACHER_ROLES,
    class_name,
    get_active_enrollment,
    get_student_or_404,
    is_class_teacher_of,
    is_parent_of,
)
from mysite.services.timeutils import (
    ABSENCE_DEADLINE,
    ABSENCE_MAX_DAYS_AHEAD,
    now_local,
)

router = APIRouter(prefix="/absence-requests", tags=["Absence Requests"])

# Окуучу бул модулдун эч бир эндпоинтине кире албайт
absence_viewer = require_roles("PARENT", *TEACHER_ROLES, *ADMIN_ROLES)


def serialize(req: AbsenceRequests) -> dict:
    return {
        "id": req.id,
        "student_id": req.student_id,
        "student_name": req.student.full_name if req.student else None,
        "parent_id": req.parent_id,
        "parent_name": req.parent.full_name if req.parent else None,
        "class_id": req.class_id,
        "class_name": class_name(req.school_class),
        "target_date": req.target_date,
        "reason": req.reason,
        "comment": req.comment,
        "status": req.status,
        "request_time": req.request_time,
        "reviewed_by": req.reviewed_by,
        "reviewed_at": req.reviewed_at,
        "review_comment": req.review_comment,
    }


def check_time_lock(target_date: date) -> None:
    """2-кадам: сервердик убакытты текшерүү (request_time < 08:00)."""
    now = now_local()
    today = now.date()

    if target_date < today:
        raise HTTPException(
            status_code=400,
            detail="Өткөн күнгө сурануу жиберүүгө болбойт",
        )

    if target_date == today and now.time() >= ABSENCE_DEADLINE:
        raise HTTPException(
            status_code=403,
            detail="Сабак башталды: бүгүнкү күнгө сурануу саат 08:00гө чейин гана кабыл алынат",
        )

    if target_date > today + timedelta(days=ABSENCE_MAX_DAYS_AHEAD):
        raise HTTPException(
            status_code=400,
            detail=f"Сурануу эң көп {ABSENCE_MAX_DAYS_AHEAD} күн алдын ала жиберилет",
        )


def get_request_or_404(db: Session, request_id: int, school_id: int) -> AbsenceRequests:
    req = db.query(AbsenceRequests).filter(
        AbsenceRequests.id == request_id,
        AbsenceRequests.school_id == school_id,
    ).first()
    if req is None:
        raise HTTPException(status_code=404, detail="Сурануу табылган жок")
    return req


def ensure_reviewer(db: Session, user: Users, req: AbsenceRequests) -> Classes:
    school_class = db.query(Classes).filter(Classes.id == req.class_id).first()
    if not is_class_teacher_of(user, school_class):
        raise HTTPException(
            status_code=403,
            detail="Суранууну өз классынын класс жетекчиси гана карайт",
        )
    return school_class


# =====================================================
# 0. Сурануу баскычынын абалы (фронтенд үчүн)
# =====================================================

@router.get("/status")
def absence_status(current_user: Users = Depends(absence_viewer)):
    now = now_local()
    return {
        "server_time": now,
        "deadline": ABSENCE_DEADLINE.strftime("%H:%M"),
        "is_open_for_today": now.time() < ABSENCE_DEADLINE,
        "can_submit": current_user.role == "PARENT",
        "max_days_ahead": ABSENCE_MAX_DAYS_AHEAD,
    }


# =====================================================
# 1. Сурануу жиберүү — АТА-ЭНЕ ГАНА
# =====================================================

@router.post("", status_code=201)
def create_absence_request(
    data: AbsenceRequestCreate,
    current_user: Users = Depends(require_roles("PARENT")),
    db: Session = Depends(get_db),
):
    now = now_local()
    target_date = data.target_date or now.date()
    check_time_lock(target_date)

    student_id = data.student_id
    if student_id is None:
        links = db.query(ParentStudents).filter(
            ParentStudents.parent_id == current_user.id
        ).all()
        if len(links) != 1:
            raise HTTPException(status_code=400, detail="student_id көрсөтүңүз")
        student_id = links[0].student_id

    if not is_parent_of(db, current_user, student_id):
        raise HTTPException(
            status_code=403,
            detail="Бул окуучу сиздин аккаунтуңузга байланышкан эмес",
        )

    student = get_student_or_404(db, student_id, current_user.school_id)
    if not student.is_active:
        raise HTTPException(status_code=400, detail="Окуучунун аккаунту активдүү эмес")

    _, school_class = get_active_enrollment(db, student.id)
    if school_class is None:
        raise HTTPException(status_code=400, detail="Окуучу эч бир класска катталган эмес")

    duplicate = db.query(AbsenceRequests.id).filter(
        AbsenceRequests.student_id == student.id,
        AbsenceRequests.target_date == target_date,
        AbsenceRequests.status.in_(["PENDING", "APPROVED"]),
    ).first()
    if duplicate:
        raise HTTPException(
            status_code=409,
            detail="Бул күнгө сурануу мурда эле жиберилген",
        )

    req = AbsenceRequests(
        student_id=student.id,
        parent_id=current_user.id,
        class_id=school_class.id,
        school_id=current_user.school_id,
        target_date=target_date,
        reason=data.reason.strip(),
        comment=data.comment.strip() if data.comment else None,
        status="PENDING",
        request_time=now,
    )
    db.add(req)
    db.flush()

    # 3-кадам: класс жетекчиге онлайн билдирүү
    day_text = "бүгүнкү күнгө" if target_date == now.date() else f"{target_date:%d.%m.%Y} күнүнө"
    notify(
        db,
        school_class.class_teacher_id,
        title="Жаңы сурануу",
        body=f"{student.full_name} {day_text} суранып жатат. Себеби: {req.reason}",
        link=f"/absence-requests/{req.id}",
    )

    db.commit()
    db.refresh(req)
    return serialize(req)


# =====================================================
# 2. Суранууларды көрүү (ролго жараша)
# =====================================================

@router.get("")
def list_absence_requests(
    status: Optional[str] = Query(default=None, pattern="^(PENDING|APPROVED|REJECTED|CANCELLED)$"),
    student_id: Optional[int] = None,
    class_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    current_user: Users = Depends(absence_viewer),
    db: Session = Depends(get_db),
):
    query = db.query(AbsenceRequests).filter(
        AbsenceRequests.school_id == current_user.school_id
    )

    if current_user.role == "PARENT":
        child_ids = [
            link.student_id
            for link in db.query(ParentStudents).filter(
                ParentStudents.parent_id == current_user.id
            )
        ]
        query = query.filter(AbsenceRequests.student_id.in_(child_ids or [-1]))

    elif current_user.role in TEACHER_ROLES:
        led_ids = [
            c.id for c in db.query(Classes).filter(
                Classes.class_teacher_id == current_user.id,
                Classes.school_id == current_user.school_id,
            )
        ]
        if not led_ids:
            raise HTTPException(
                status_code=403,
                detail="Суранууларды класс жетекчилер гана көрөт",
            )
        query = query.filter(AbsenceRequests.class_id.in_(led_ids))

    # ADMIN_ROLES — бүт мектеп боюнча көзөмөл

    if status:
        query = query.filter(AbsenceRequests.status == status)
    if student_id:
        query = query.filter(AbsenceRequests.student_id == student_id)
    if class_id:
        query = query.filter(AbsenceRequests.class_id == class_id)
    if date_from:
        query = query.filter(AbsenceRequests.target_date >= date_from)
    if date_to:
        query = query.filter(AbsenceRequests.target_date <= date_to)

    requests = query.order_by(
        AbsenceRequests.target_date.desc(),
        AbsenceRequests.request_time.desc(),
    ).all()

    return [serialize(r) for r in requests]


@router.get("/{request_id}")
def get_absence_request(
    request_id: int,
    current_user: Users = Depends(absence_viewer),
    db: Session = Depends(get_db),
):
    req = get_request_or_404(db, request_id, current_user.school_id)

    allowed = (
        current_user.role in ADMIN_ROLES
        or (current_user.role == "PARENT" and is_parent_of(db, current_user, req.student_id))
        or is_class_teacher_of(current_user, req.school_class)
    )
    if not allowed:
        raise HTTPException(status_code=403, detail="Бул суранууну көрүүгө уруксат жок")

    return serialize(req)


# =====================================================
# 3. Уруксат берүү — класс жетекчи (журналга «С»)
# =====================================================

def apply_excused_mark(db: Session, req: AbsenceRequests) -> int:
    """Ошол күнкү класстын БАРДЫК сабактарындагы жазууларды «С» кылат.

    Мугалим ал күнгө жазуу кийин киргизсе дагы, журнал API бекитилген
    суранууну текшерип «С» белгисин автоматтык коёт.
    """
    entries = (
        db.query(JournalEntries)
        .join(TeacherAssignments, TeacherAssignments.id == JournalEntries.assignment_id)
        .filter(
            JournalEntries.student_id == req.student_id,
            JournalEntries.date == req.target_date,
            TeacherAssignments.class_id == req.class_id,
        )
        .all()
    )

    pairs = set()
    for entry in entries:
        entry.attendance = "С"
        entry.grade_value = None
        pairs.add((req.student_id, entry.assignment.subject_id))

    if pairs:
        db.flush()
        recompute_subject_xp(db, req.school_id, pairs)
        sync_badges(db, req.school_id)

    return len(entries)


@router.post("/{request_id}/approve")
def approve_absence_request(
    request_id: int,
    data: Optional[AbsenceReview] = None,
    current_user: Users = Depends(require_roles(*TEACHER_ROLES)),
    db: Session = Depends(get_db),
):
    req = get_request_or_404(db, request_id, current_user.school_id)
    ensure_reviewer(db, current_user, req)

    if req.status != "PENDING":
        raise HTTPException(status_code=400, detail="Бул суранууга мурда эле чечим чыгарылган")

    req.status = "APPROVED"
    req.reviewed_by = current_user.id
    req.reviewed_at = now_local()
    req.review_comment = data.comment if data else None

    updated = apply_excused_mark(db, req)

    notify(
        db,
        req.parent_id,
        title="Сурануу кабыл алынды",
        body=f"{req.student.full_name}: {req.target_date:%d.%m.%Y} күнү себептүү («С») деп белгиленди",
        link=f"/absence-requests/{req.id}",
    )

    db.commit()
    db.refresh(req)

    result = serialize(req)
    result["journal_entries_marked"] = updated
    return result


# =====================================================
# 4. Четке кагуу — класс жетекчи
# =====================================================

@router.post("/{request_id}/reject")
def reject_absence_request(
    request_id: int,
    data: Optional[AbsenceReview] = None,
    current_user: Users = Depends(require_roles(*TEACHER_ROLES)),
    db: Session = Depends(get_db),
):
    req = get_request_or_404(db, request_id, current_user.school_id)
    ensure_reviewer(db, current_user, req)

    if req.status != "PENDING":
        raise HTTPException(status_code=400, detail="Бул суранууга мурда эле чечим чыгарылган")

    req.status = "REJECTED"
    req.reviewed_by = current_user.id
    req.reviewed_at = now_local()
    req.review_comment = data.comment if data else None

    notify(
        db,
        req.parent_id,
        title="Сурануу четке кагылды",
        body=(
            f"{req.student.full_name}: {req.target_date:%d.%m.%Y}"
            + (f". Себеби: {req.review_comment}" if req.review_comment else "")
        ),
        link=f"/absence-requests/{req.id}",
    )

    db.commit()
    db.refresh(req)
    return serialize(req)


# =====================================================
# 5. Жокко чыгаруу — ата-эне (каралбаган сурануу гана)
# =====================================================

@router.post("/{request_id}/cancel")
def cancel_absence_request(
    request_id: int,
    current_user: Users = Depends(require_roles("PARENT")),
    db: Session = Depends(get_db),
):
    req = get_request_or_404(db, request_id, current_user.school_id)

    if req.parent_id != current_user.id:
        raise HTTPException(status_code=403, detail="Бул сурануу сиз тарабыңыздан жиберилген эмес")

    if req.status != "PENDING":
        raise HTTPException(status_code=400, detail="Каралып бүткөн суранууну жокко чыгарууга болбойт")

    req.status = "CANCELLED"
    db.commit()
    db.refresh(req)
    return serialize(req)

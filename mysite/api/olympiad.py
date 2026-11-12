"""Олимпиадалык аналитика жана талапкерлерди тандоо (ТЗ 4.2).

  * Директор/Завуч — талапкерди ТАНДАЙТ (SELECTED).
  * Класс жетекчи/мугалим — СУНУШТАЙТ (SUGGESTED), завуч бекитет.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mysite.db.database import get_db
from mysite.db.models import OlympiadCandidates, Subjects, TeacherAssignments, Users
from mysite.db.schema import OlympiadAutoSelect, OlympiadCandidateCreate
from mysite.security.permissions import require_roles
from mysite.services.notifications import notify
from mysite.services.rating import OLYMPIAD_TOP_N, load_scores, rank, sync_badges
from mysite.services.school import (
    ADMIN_ROLES,
    STAFF_ROLES,
    get_active_enrollment,
    get_student_or_404,
)
from mysite.services.timeutils import current_academic_year

router = APIRouter(prefix="/olympiad", tags=["Olympiad"])


def get_subject(db: Session, subject_id: int, school_id: int) -> Subjects:
    subject = db.query(Subjects).filter(
        Subjects.id == subject_id, Subjects.school_id == school_id
    ).first()
    if subject is None:
        raise HTTPException(status_code=404, detail="Предмет табылган жок")
    return subject


def student_year(db: Session, student_id: int) -> str:
    enrollment, _ = get_active_enrollment(db, student_id)
    return enrollment.academic_year if enrollment else current_academic_year()


def serialize(db: Session, c: OlympiadCandidates, names: dict, subjects: dict) -> dict:
    return {
        "id": c.id,
        "subject_id": c.subject_id,
        "subject_name": subjects.get(c.subject_id),
        "student_id": c.student_id,
        "student_name": names.get(c.student_id),
        "academic_year": c.academic_year,
        "status": c.status,
        "suggested_by": c.suggested_by,
        "approved_by": c.approved_by,
        "note": c.note,
        "created_at": c.created_at,
    }


def _lookups(db: Session, school_id: int):
    subjects = {s.id: s.name for s in db.query(Subjects).filter(Subjects.school_id == school_id)}
    names = {
        u.id: u.full_name
        for u in db.query(Users.id, Users.full_name).filter(
            Users.school_id == school_id, Users.role == "STUDENT"
        )
    }
    return names, subjects


# 1. Аналитика: предмет боюнча автоматтык Топ-N жана алардын статусу
@router.get("/analytics")
def olympiad_analytics(
    subject_id: Optional[int] = None,
    grade_number: Optional[int] = Query(default=None, ge=1, le=11),
    limit: int = Query(default=OLYMPIAD_TOP_N, ge=1, le=20),
    current_user: Users = Depends(require_roles(*STAFF_ROLES)),
    db: Session = Depends(get_db),
):
    school_id = current_user.school_id
    scores = load_scores(db, school_id)

    query = db.query(Subjects).filter(Subjects.school_id == school_id)
    if subject_id:
        query = query.filter(Subjects.id == subject_id)
    subjects = query.order_by(Subjects.name).all()
    if subject_id and not subjects:
        raise HTTPException(status_code=404, detail="Предмет табылган жок")

    statuses = {
        (c.subject_id, c.student_id): c
        for c in db.query(OlympiadCandidates).filter(OlympiadCandidates.school_id == school_id)
    }

    result = []
    for subject in subjects:
        top = [
            r for r in rank(scores, subject_id=subject.id, grade_number=grade_number)
            if r["xp"] > 0
        ][:limit]
        for row in top:
            candidate = statuses.get((subject.id, row["student_id"]))
            row["candidate_id"] = candidate.id if candidate else None
            row["candidate_status"] = candidate.status if candidate else None
        result.append({
            "subject_id": subject.id,
            "subject_name": subject.name,
            "top": top,
        })

    return {"grade_number": grade_number, "subjects": result}


# 2. Талапкерлердин тизмеси
@router.get("/candidates")
def list_candidates(
    subject_id: Optional[int] = None,
    status: Optional[str] = Query(default=None, pattern="^(SUGGESTED|SELECTED)$"),
    academic_year: Optional[str] = None,
    current_user: Users = Depends(require_roles(*STAFF_ROLES)),
    db: Session = Depends(get_db),
):
    query = db.query(OlympiadCandidates).filter(
        OlympiadCandidates.school_id == current_user.school_id
    )
    if subject_id:
        query = query.filter(OlympiadCandidates.subject_id == subject_id)
    if status:
        query = query.filter(OlympiadCandidates.status == status)
    if academic_year:
        query = query.filter(OlympiadCandidates.academic_year == academic_year)

    names, subjects = _lookups(db, current_user.school_id)
    return [
        serialize(db, c, names, subjects)
        for c in query.order_by(OlympiadCandidates.subject_id, OlympiadCandidates.id)
    ]


# 3. Талапкер кошуу: завуч — тандайт, мугалим — сунуштайт
@router.post("/candidates", status_code=201)
def add_candidate(
    data: OlympiadCandidateCreate,
    current_user: Users = Depends(require_roles(*STAFF_ROLES)),
    db: Session = Depends(get_db),
):
    school_id = current_user.school_id
    subject = get_subject(db, data.subject_id, school_id)
    student = get_student_or_404(db, data.student_id, school_id)
    is_admin = current_user.role in ADMIN_ROLES

    if not is_admin:
        # Предметтик мугалим өз предметине, класс жетекчи өз классынын окуучусун сунуштайт
        _, school_class = get_active_enrollment(db, student.id)
        teaches_subject = db.query(TeacherAssignments.id).filter(
            TeacherAssignments.teacher_id == current_user.id,
            TeacherAssignments.subject_id == subject.id,
        ).first() is not None
        leads_class = school_class is not None and school_class.class_teacher_id == current_user.id
        if not (teaches_subject or leads_class):
            raise HTTPException(
                status_code=403,
                detail="Өз предметиңиз же өз классыңыздын окуучусун гана сунуштай аласыз",
            )

    year = student_year(db, student.id)
    candidate = db.query(OlympiadCandidates).filter(
        OlympiadCandidates.subject_id == subject.id,
        OlympiadCandidates.student_id == student.id,
        OlympiadCandidates.academic_year == year,
    ).first()

    if candidate is not None:
        if candidate.status == "SELECTED" or not is_admin:
            raise HTTPException(status_code=409, detail="Бул окуучу тизмеде мурда эле бар")
        candidate.status = "SELECTED"
        candidate.approved_by = current_user.id
    else:
        candidate = OlympiadCandidates(
            school_id=school_id,
            subject_id=subject.id,
            student_id=student.id,
            academic_year=year,
            status="SELECTED" if is_admin else "SUGGESTED",
            suggested_by=current_user.id,
            approved_by=current_user.id if is_admin else None,
            note=data.note,
        )
        db.add(candidate)

    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Бул окуучу тизмеде мурда эле бар")

    if candidate.status == "SELECTED":
        notify(
            db, student.id,
            title="Олимпиадалык курам",
            body=f"Сиз «{subject.name}» боюнча мектептин олимпиадалык курамына кирдиңиз!",
        )
    sync_badges(db, school_id)
    db.commit()
    db.refresh(candidate)

    names, subjects = _lookups(db, school_id)
    return serialize(db, candidate, names, subjects)


# 4. Сунушту бекитүү (Завуч / Директор)
@router.post("/candidates/{candidate_id}/approve")
def approve_candidate(
    candidate_id: int,
    current_user: Users = Depends(require_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    candidate = db.query(OlympiadCandidates).filter(
        OlympiadCandidates.id == candidate_id,
        OlympiadCandidates.school_id == current_user.school_id,
    ).first()
    if candidate is None:
        raise HTTPException(status_code=404, detail="Талапкер табылган жок")
    if candidate.status == "SELECTED":
        raise HTTPException(status_code=400, detail="Талапкер мурда эле тандалган")

    candidate.status = "SELECTED"
    candidate.approved_by = current_user.id
    db.flush()
    sync_badges(db, current_user.school_id)
    db.commit()
    db.refresh(candidate)

    names, subjects = _lookups(db, current_user.school_id)
    return serialize(db, candidate, names, subjects)


# 5. Топ-N окуучуну автоматтык тандоо (Завуч / Директор)
@router.post("/auto-select")
def auto_select(
    data: OlympiadAutoSelect,
    current_user: Users = Depends(require_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    school_id = current_user.school_id
    subject = get_subject(db, data.subject_id, school_id)
    scores = load_scores(db, school_id)
    top = [
        r for r in rank(scores, subject_id=subject.id, grade_number=data.grade_number)
        if r["xp"] > 0
    ][:data.limit]

    selected = []
    for row in top:
        year = student_year(db, row["student_id"])
        candidate = db.query(OlympiadCandidates).filter(
            OlympiadCandidates.subject_id == subject.id,
            OlympiadCandidates.student_id == row["student_id"],
            OlympiadCandidates.academic_year == year,
        ).first()
        if candidate is None:
            candidate = OlympiadCandidates(
                school_id=school_id,
                subject_id=subject.id,
                student_id=row["student_id"],
                academic_year=year,
                suggested_by=current_user.id,
            )
            db.add(candidate)
        candidate.status = "SELECTED"
        candidate.approved_by = current_user.id
        selected.append(row)

    db.flush()
    sync_badges(db, school_id)
    db.commit()

    return {
        "message": "Талапкерлер автоматтык тандалды",
        "subject_id": subject.id,
        "subject_name": subject.name,
        "selected": selected,
    }


# 6. Тизмеден алып салуу
@router.delete("/candidates/{candidate_id}")
def remove_candidate(
    candidate_id: int,
    current_user: Users = Depends(require_roles(*STAFF_ROLES)),
    db: Session = Depends(get_db),
):
    candidate = db.query(OlympiadCandidates).filter(
        OlympiadCandidates.id == candidate_id,
        OlympiadCandidates.school_id == current_user.school_id,
    ).first()
    if candidate is None:
        raise HTTPException(status_code=404, detail="Талапкер табылган жок")

    if current_user.role not in ADMIN_ROLES:
        if candidate.status != "SUGGESTED" or candidate.suggested_by != current_user.id:
            raise HTTPException(status_code=403, detail="Өз сунушуңузду гана кайтарып ала аласыз")

    db.delete(candidate)
    db.flush()
    sync_badges(db, current_user.school_id)
    db.commit()
    return {"message": "Талапкер тизмеден алынды"}

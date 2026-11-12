"""Көп баскычтуу рейтинг (ТЗ 4.1): класс, параллель, предмет, мектеп."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from mysite.db.database import get_db
from mysite.db.models import (
    JournalEntries,
    Subjects,
    SubjectXP,
    TeacherAssignments,
    UserBadges,
    Users,
)
from mysite.security.permissions import get_current_user, require_roles
from mysite.services.rating import (
    OLYMPIAD_TOP_N,
    load_scores,
    rank,
    recompute_subject_xp,
    sync_badges,
)
from mysite.services.school import (
    ADMIN_ROLES,
    STAFF_ROLES,
    class_name,
    get_class_or_404,
    resolve_student_for_viewer,
)

router = APIRouter(prefix="/ratings", tags=["Ratings"])


def get_subject_or_404(db: Session, subject_id: int, school_id: int) -> Subjects:
    subject = db.query(Subjects).filter(
        Subjects.id == subject_id, Subjects.school_id == school_id
    ).first()
    if subject is None:
        raise HTTPException(status_code=404, detail="Предмет табылган жок")
    return subject


def subject_info(db: Session, subject_id: Optional[int], school_id: int):
    if subject_id is None:
        return None
    subject = get_subject_or_404(db, subject_id, school_id)
    return {"id": subject.id, "name": subject.name}


# 1. Класс ичиндеги рейтинг
@router.get("/class/{class_id}")
def class_rating(
    class_id: int,
    subject_id: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    school_class = get_class_or_404(db, class_id, current_user.school_id)
    scores = load_scores(db, current_user.school_id)
    return {
        "scope": "class",
        "class_id": class_id,
        "class_name": class_name(school_class),
        "subject": subject_info(db, subject_id, current_user.school_id),
        "items": rank(scores, subject_id=subject_id, class_id=class_id),
    }


# 2. Параллелдер рейтинги (мис: бардык 11-класстар)
@router.get("/parallel/{grade}")
def parallel_rating(
    grade: int,
    subject_id: Optional[int] = None,
    limit: int = Query(default=100, ge=1, le=1000),
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not 1 <= grade <= 11:
        raise HTTPException(status_code=400, detail="Класс 1ден 11ге чейин болушу керек")
    scores = load_scores(db, current_user.school_id)
    return {
        "scope": "parallel",
        "grade_number": grade,
        "subject": subject_info(db, subject_id, current_user.school_id),
        "items": rank(scores, subject_id=subject_id, grade_number=grade)[:limit],
    }


# 3. Мектеп боюнча жалпы рейтинг
@router.get("/school")
def school_rating(
    limit: int = Query(default=100, ge=1, le=1000),
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scores = load_scores(db, current_user.school_id)
    return {"scope": "school", "items": rank(scores)[:limit]}


# 4. Предметтик рейтинг
@router.get("/subjects/{subject_id}")
def subject_rating(
    subject_id: int,
    grade_number: Optional[int] = Query(default=None, ge=1, le=11),
    class_id: Optional[int] = None,
    limit: int = Query(default=100, ge=1, le=1000),
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scores = load_scores(db, current_user.school_id)
    return {
        "scope": "subject",
        "subject": subject_info(db, subject_id, current_user.school_id),
        "grade_number": grade_number,
        "class_id": class_id,
        "items": rank(
            scores, subject_id=subject_id, grade_number=grade_number, class_id=class_id
        )[:limit],
    }


# 5. Предмет боюнча Топ окуучулар — олимпиадалык талапкерлер (Завуч / Мугалим)
@router.get("/subjects/{subject_id}/top")
def subject_top(
    subject_id: int,
    grade_number: Optional[int] = Query(default=None, ge=1, le=11),
    limit: int = Query(default=OLYMPIAD_TOP_N, ge=1, le=50),
    current_user: Users = Depends(require_roles(*STAFF_ROLES)),
    db: Session = Depends(get_db),
):
    scores = load_scores(db, current_user.school_id)
    items = [
        row for row in rank(scores, subject_id=subject_id, grade_number=grade_number)
        if row["xp"] > 0
    ][:limit]
    return {
        "subject": subject_info(db, subject_id, current_user.school_id),
        "grade_number": grade_number,
        "items": items,
    }


# 6. Окуучунун бардык рейтингдеги орду + значоктору
def student_standing(db: Session, student: Users) -> dict:
    scores = load_scores(db, student.school_id)
    me = next((s for s in scores if s.student_id == student.id), None)

    badges = db.query(UserBadges).filter(UserBadges.user_id == student.id).all()
    subjects = {
        s.id: s.name
        for s in db.query(Subjects).filter(Subjects.school_id == student.school_id)
    }
    badge_list = [
        {
            "badge_type": b.badge_type,
            "icon_name": b.icon_name,
            "subject_id": b.subject_id,
            "subject_name": subjects.get(b.subject_id),
            "awarded_at": b.awarded_at,
        }
        for b in badges
    ]

    if me is None:
        return {
            "student_id": student.id,
            "full_name": student.full_name,
            "class_id": None,
            "class_name": None,
            "total_xp": 0,
            "class_rank": None,
            "parallel_rank": None,
            "school_rank": None,
            "subjects": [],
            "badges": badge_list,
        }

    def position(ranking):
        return next((r["rank"] for r in ranking if r["student_id"] == student.id), None)

    subject_rows = []
    for subject_id, xp in sorted(me.subject_xp.items(), key=lambda kv: -kv[1]):
        subject_rows.append({
            "subject_id": subject_id,
            "subject_name": subjects.get(subject_id),
            "xp": xp,
            "class_rank": position(rank(scores, subject_id=subject_id, class_id=me.class_id)),
            "parallel_rank": position(rank(scores, subject_id=subject_id, grade_number=me.grade_number)),
            "school_rank": position(rank(scores, subject_id=subject_id)),
        })

    return {
        "student_id": student.id,
        "full_name": student.full_name,
        "avatar_url": student.avatar_url,
        "class_id": me.class_id,
        "class_name": me.class_name,
        "grade_number": me.grade_number,
        "total_xp": me.total_xp,
        "class_rank": position(rank(scores, class_id=me.class_id)),
        "parallel_rank": position(rank(scores, grade_number=me.grade_number)),
        "school_rank": position(rank(scores)),
        "subjects": subject_rows,
        "badges": badge_list,
    }


@router.get("/me")
def my_standing(
    student_id: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    student = resolve_student_for_viewer(db, current_user, student_id)
    return student_standing(db, student)


# 7. XP жана значокторду журналдан толук кайра эсептөө (Завуч / Директор)
@router.post("/recompute")
def recompute_all(
    current_user: Users = Depends(require_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    school_id = current_user.school_id

    pairs = {
        (student_id, subject_id)
        for student_id, subject_id in db.query(
            JournalEntries.student_id, TeacherAssignments.subject_id
        )
        .join(TeacherAssignments, TeacherAssignments.id == JournalEntries.assignment_id)
        .filter(JournalEntries.school_id == school_id)
        .distinct()
    }
    pairs |= {
        (x.student_id, x.subject_id)
        for x in db.query(SubjectXP).filter(SubjectXP.school_id == school_id)
    }

    recompute_subject_xp(db, school_id, pairs)
    sync_badges(db, school_id)
    db.commit()
    return {"message": "Рейтинг кайра эсептелди", "recomputed": len(pairs)}

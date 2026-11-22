"""Мугалимдердин тизмеси жана башкаруу (Директор / Завуч).

    GET    /teachers                 — мектептин мугалимдери (класс жетекчилиги, сабактары менен)
    GET    /teachers/{id}            — бир мугалим
    PUT    /teachers/{id}            — аты-жөнүн, телефонун өзгөртүү
    DELETE /teachers/{id}            — активсиз кылуу (маалымат өчпөйт)
    POST   /teachers/{id}/activate   — кайра активдештирүү

Кошуу: POST /users/create-teacher, Excel: POST /admin/excel/import-teachers.
"""
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from mysite.db.database import get_db
from mysite.db.models import Classes, TeacherAssignments, Users
from mysite.db.schema import TeacherUpdate
from mysite.security.permissions import require_roles
from mysite.services.school import ADMIN_ROLES, TEACHER_ROLES, class_name

router = APIRouter(prefix="/teachers", tags=["Teachers"])


def serialize_teachers(db: Session, teachers: list[Users]) -> list[dict]:
    ids = [t.id for t in teachers] or [-1]

    led = defaultdict(list)
    for c in db.query(Classes).filter(Classes.class_teacher_id.in_(ids)):
        led[c.class_teacher_id].append({
            "id": c.id,
            "name": class_name(c),
            "academic_year": c.academic_year,
        })

    assignments = defaultdict(list)
    for a in db.query(TeacherAssignments).filter(TeacherAssignments.teacher_id.in_(ids)):
        assignments[a.teacher_id].append({
            "id": a.id,
            "class_id": a.class_id,
            "class_name": class_name(a.school_class),
            "subject_id": a.subject_id,
            "subject_name": a.subject.name if a.subject else None,
            "academic_year": a.academic_year,
        })

    return [
        {
            "id": t.id,
            "email": t.email,
            "full_name": t.full_name,
            "avatar_url": t.avatar_url,
            "role": t.role,
            "is_active": t.is_active,
            "is_temp_password": t.is_temp_password,
            "created_at": t.created_at,
            "is_class_teacher": bool(led[t.id]),
            "classes_led": led[t.id],
            "assignments": sorted(
                assignments[t.id],
                key=lambda x: (x["class_name"] or "", x["subject_name"] or ""),
            ),
        }
        for t in teachers
    ]


def get_teacher_or_404(db: Session, teacher_id: int, school_id: int) -> Users:
    teacher = db.query(Users).filter(
        Users.id == teacher_id,
        Users.school_id == school_id,
        Users.role.in_(TEACHER_ROLES),
    ).first()
    if teacher is None:
        raise HTTPException(status_code=404, detail="Мугалим табылган жок")
    return teacher


@router.get("")
def list_teachers(
    search: Optional[str] = None,
    include_inactive: bool = False,
    current_user: Users = Depends(require_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    query = db.query(Users).filter(
        Users.school_id == current_user.school_id,
        Users.role.in_(TEACHER_ROLES),
    )
    if not include_inactive:
        query = query.filter(Users.is_active.is_(True))
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        query = query.filter(or_(Users.full_name.ilike(pattern), Users.email.like(pattern)))

    return serialize_teachers(db, query.order_by(Users.full_name).all())


@router.get("/{teacher_id}")
def get_teacher(
    teacher_id: int,
    current_user: Users = Depends(require_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    teacher = get_teacher_or_404(db, teacher_id, current_user.school_id)
    return serialize_teachers(db, [teacher])[0]


@router.put("/{teacher_id}")
def update_teacher(
    teacher_id: int,
    data: TeacherUpdate,
    current_user: Users = Depends(require_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    teacher = get_teacher_or_404(db, teacher_id, current_user.school_id)
    update = data.model_dump(exclude_unset=True)
    if not update:
        raise HTTPException(status_code=400, detail="Өзгөртүү үчүн маалымат берилген жок")

    if update.get("full_name"):
        teacher.full_name = update["full_name"].strip()

    db.commit()
    db.refresh(teacher)
    return serialize_teachers(db, [teacher])[0]


@router.delete("/{teacher_id}")
def deactivate_teacher(
    teacher_id: int,
    current_user: Users = Depends(require_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    teacher = get_teacher_or_404(db, teacher_id, current_user.school_id)

    teacher.is_active = False
    # Иштебей калган мугалим класс жетекчи боюнча калбашы керек
    released = db.query(Classes).filter(Classes.class_teacher_id == teacher.id).update(
        {"class_teacher_id": None}
    )
    db.commit()

    return {
        "message": "Мугалим активсиз кылынды",
        "teacher_id": teacher.id,
        "classes_released": released,
    }


@router.post("/{teacher_id}/activate")
def activate_teacher(
    teacher_id: int,
    current_user: Users = Depends(require_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    teacher = get_teacher_or_404(db, teacher_id, current_user.school_id)
    teacher.is_active = True
    db.commit()
    db.refresh(teacher)
    return serialize_teachers(db, [teacher])[0]

"""Платформанын администратору (SYSTEM_ADMIN) — бардык мектептердин үстүндө.

Мектептерди кошуу, өзгөртүү, жабуу; ар бир мектептин директорун жана
завучтарын дайындоо, алардын сыр сөздөрүн баштапкы абалга келтирүү.
Мектептин ичиндеги иштерди (класстар, мугалимдер, журнал) директор жүргүзөт.

Биринчи SYSTEM_ADMIN серверде скрипт менен түзүлөт:
    docker compose exec api python create_system_admin.py --email ... --name "..."
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from mysite.db.database import get_db
from mysite.db.models import Classes, Schools, Users
from mysite.db.schema import SchoolAdminWithRole, SchoolUpdate, SystemSchoolCreate
from mysite.security.permissions import require_roles
from mysite.services.accounts import admin_row, create_school_admin, ensure_admin_limit
from mysite.services.passwords import set_temp_password
from mysite.services.school import ADMIN_ROLES, TEACHER_ROLES

router = APIRouter(prefix="/system", tags=["System Admin"])

system_admin = require_roles("SYSTEM_ADMIN")


def get_school_or_404(db: Session, school_id: int) -> Schools:
    school = db.query(Schools).filter(Schools.id == school_id).first()
    if school is None:
        raise HTTPException(status_code=404, detail="Мектеп табылган жок")
    return school


def count_by_school(db: Session, roles) -> dict[int, int]:
    return dict(
        db.query(Users.school_id, func.count(Users.id))
        .filter(Users.role.in_(roles), Users.is_active.is_(True))
        .group_by(Users.school_id)
        .all()
    )


def serialize_school(school: Schools, students=0, teachers=0, classes=0, admins=None) -> dict:
    data = {
        "id": school.id,
        "name": school.name,
        "email": school.email,
        "logo_url": school.logo_url,
        "banner_url": school.banner_url,
        "director_name": school.director_name,
        "is_active": school.is_active,
        "created_at": school.created_at,
        "stats": {"students": students, "teachers": teachers, "classes": classes},
    }
    if admins is not None:
        data["admins"] = admins
    return data


def school_admins(db: Session, school_id: int) -> list[dict]:
    users = db.query(Users).filter(
        Users.school_id == school_id,
        Users.role.in_(ADMIN_ROLES),
    ).order_by(Users.role, Users.full_name).all()
    return [admin_row(u) for u in users]


# =====================================================
# Платформанын статистикасы
# =====================================================

@router.get("/stats")
def platform_stats(
    current_user: Users = Depends(system_admin),
    db: Session = Depends(get_db),
):
    by_role = dict(
        db.query(Users.role, func.count(Users.id))
        .filter(Users.is_active.is_(True))
        .group_by(Users.role)
        .all()
    )
    return {
        "schools": db.query(func.count(Schools.id)).scalar() or 0,
        "active_schools": db.query(func.count(Schools.id)).filter(Schools.is_active.is_(True)).scalar() or 0,
        "directors": by_role.get("DIRECTOR", 0),
        "deputies": by_role.get("DEPUTY", 0),
        "teachers": by_role.get("TEACHER", 0) + by_role.get("CLASS_TEACHER", 0),
        "students": by_role.get("STUDENT", 0),
        "parents": by_role.get("PARENT", 0),
    }


# =====================================================
# Мектептер
# =====================================================

@router.get("/schools")
def list_schools(
    search: Optional[str] = None,
    include_inactive: bool = True,
    current_user: Users = Depends(system_admin),
    db: Session = Depends(get_db),
):
    query = db.query(Schools)
    if not include_inactive:
        query = query.filter(Schools.is_active.is_(True))
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        query = query.filter(Schools.name.ilike(pattern))

    students = count_by_school(db, ["STUDENT"])
    teachers = count_by_school(db, list(TEACHER_ROLES))
    classes = dict(
        db.query(Classes.school_id, func.count(Classes.id)).group_by(Classes.school_id).all()
    )

    return [
        serialize_school(
            s, students.get(s.id, 0), teachers.get(s.id, 0), classes.get(s.id, 0)
        )
        for s in query.order_by(Schools.name).all()
    ]


@router.post("/schools", status_code=201)
def create_school(
    data: SystemSchoolCreate,
    current_user: Users = Depends(system_admin),
    db: Session = Depends(get_db),
):
    """Жаңы мектеп + анын директору (убактылуу сыр сөз кайтат)."""
    fields = data.model_dump(exclude={"director"})
    school = Schools(**fields)
    if not school.director_name:
        school.director_name = data.director.full_name
    db.add(school)
    db.flush()

    try:
        director, password = create_school_admin(
            db,
            school_id=school.id,
            email=data.director.email,
            full_name=data.director.full_name,
            role="DIRECTOR",
        )
    except HTTPException:
        db.rollback()  # мектеп да түзүлбөй калсын
        raise
    db.commit()
    db.refresh(school)

    return {
        "message": "Мектеп жана директор түзүлдү",
        "school": serialize_school(school, admins=school_admins(db, school.id)),
        "director": {
            "id": director.id,
            "email": director.email,
            "full_name": director.full_name,
            "temporary_password": password,
        },
    }


@router.get("/schools/{school_id}")
def get_school(
    school_id: int,
    current_user: Users = Depends(system_admin),
    db: Session = Depends(get_db),
):
    school = get_school_or_404(db, school_id)
    students = count_by_school(db, ["STUDENT"]).get(school.id, 0)
    teachers = count_by_school(db, list(TEACHER_ROLES)).get(school.id, 0)
    classes = db.query(func.count(Classes.id)).filter(Classes.school_id == school.id).scalar() or 0
    return serialize_school(school, students, teachers, classes, admins=school_admins(db, school.id))


@router.put("/schools/{school_id}")
def update_school(
    school_id: int,
    data: SchoolUpdate,
    current_user: Users = Depends(system_admin),
    db: Session = Depends(get_db),
):
    school = get_school_or_404(db, school_id)
    update = data.model_dump(exclude_unset=True)
    if not update:
        raise HTTPException(status_code=400, detail="Өзгөртүү үчүн маалымат берилген жок")
    for key, value in update.items():
        setattr(school, key, value)
    db.commit()
    db.refresh(school)
    return serialize_school(school, admins=school_admins(db, school.id))


@router.post("/schools/{school_id}/deactivate")
def deactivate_school(
    school_id: int,
    current_user: Users = Depends(system_admin),
    db: Session = Depends(get_db),
):
    """Мектепти жабат: анын колдонуучулары кире албай калат, маалымат сакталат."""
    school = get_school_or_404(db, school_id)
    school.is_active = False
    db.commit()
    return {"message": "Мектеп убактылуу жабылды", "school_id": school.id, "is_active": False}


@router.post("/schools/{school_id}/activate")
def activate_school(
    school_id: int,
    current_user: Users = Depends(system_admin),
    db: Session = Depends(get_db),
):
    school = get_school_or_404(db, school_id)
    school.is_active = True
    db.commit()
    return {"message": "Мектеп кайра ачылды", "school_id": school.id, "is_active": True}


# =====================================================
# Мектептин жетекчилери (директор, завуч)
# =====================================================

@router.get("/schools/{school_id}/admins")
def list_school_admins(
    school_id: int,
    current_user: Users = Depends(system_admin),
    db: Session = Depends(get_db),
):
    get_school_or_404(db, school_id)
    return school_admins(db, school_id)


@router.post("/schools/{school_id}/admins", status_code=201)
def add_school_admin(
    school_id: int,
    data: SchoolAdminWithRole,
    current_user: Users = Depends(system_admin),
    db: Session = Depends(get_db),
):
    school = get_school_or_404(db, school_id)
    try:
        user, password = create_school_admin(
            db,
            school_id=school.id,
            email=data.email,
            full_name=data.full_name,
            role=data.role,
        )
    except HTTPException:
        db.rollback()
        raise
    db.commit()
    db.refresh(user)
    return {**admin_row(user), "temporary_password": password}


def get_admin_user_or_404(db: Session, user_id: int) -> Users:
    user = db.query(Users).filter(
        Users.id == user_id,
        Users.role.in_(ADMIN_ROLES),
    ).first()
    if user is None:
        raise HTTPException(status_code=404, detail="Директор же завуч табылган жок")
    return user


@router.post("/users/{user_id}/reset-password")
def reset_admin_password(
    user_id: int,
    current_user: Users = Depends(system_admin),
    db: Session = Depends(get_db),
):
    user = get_admin_user_or_404(db, user_id)
    password = set_temp_password(user)
    db.commit()
    return {
        "message": "Сыр сөз баштапкы абалга келтирилди",
        "user_id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "temporary_password": password,
    }


@router.post("/users/{user_id}/deactivate")
def deactivate_admin(
    user_id: int,
    current_user: Users = Depends(system_admin),
    db: Session = Depends(get_db),
):
    user = get_admin_user_or_404(db, user_id)
    user.is_active = False
    db.commit()
    return {"message": "Аккаунт активсиз кылынды", "user_id": user.id}


@router.post("/users/{user_id}/activate")
def activate_admin(
    user_id: int,
    current_user: Users = Depends(system_admin),
    db: Session = Depends(get_db),
):
    user = get_admin_user_or_404(db, user_id)
    if not user.is_active:
        # Кайра күйгүзүү да директор/завуч чегинен ашпашы керек
        ensure_admin_limit(db, user.school_id, user.role)
    user.is_active = True
    db.commit()
    return {"message": "Аккаунт кайра активдештирилди", "user_id": user.id}

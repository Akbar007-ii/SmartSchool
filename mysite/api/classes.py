
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from mysite.db.database import get_db
from mysite.db.models import Classes, Users
from mysite.db.schema import ClassCreate, ClassOut,ClassTeacherAssign
from mysite.security.permissions import (
    get_current_user,
    require_roles
)

router = APIRouter(
    prefix="/classes",
    tags=["Classes"]
)


# Мектептеги бардык класстарды көрүү
@router.get("/", response_model=list[ClassOut])
def get_classes(
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    classes = db.query(Classes).filter(
        Classes.school_id == current_user.school_id
    ).order_by(
        Classes.grade_number,
        Classes.letter
    ).all()

    return classes


# Жаңы класс түзүү
@router.post("/", response_model=ClassOut)
def create_class(
    data: ClassCreate,
    current_user: Users = Depends(
        require_roles("DIRECTOR", "DEPUTY")
    ),
    db: Session = Depends(get_db)
):
    # Класс жетекчини текшерүү
    if data.class_teacher_id is not None:
        teacher = db.query(Users).filter(
            Users.id == data.class_teacher_id,
            Users.school_id == current_user.school_id,
            Users.role.in_(["CLASS_TEACHER", "TEACHER"]),
            Users.is_active == True
        ).first()

        if not teacher:
            raise HTTPException(
                status_code=404,
                detail="Класс жетекчи табылган жок"
            )

    new_class = Classes(
        grade_number=data.grade_number,
        letter=data.letter,
        school_id=current_user.school_id,
        class_teacher_id=data.class_teacher_id,
        academic_year=data.academic_year
    )

    db.add(new_class)

    try:
        db.commit()
        db.refresh(new_class)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Бул класс мурда түзүлгөн"
        )

    return new_class


# Белгилүү бир классты көрүү
@router.get("/{class_id}", response_model=ClassOut)
def get_class(
    class_id: int,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    school_class = db.query(Classes).filter(
        Classes.id == class_id,
        Classes.school_id == current_user.school_id
    ).first()

    if not school_class:
        raise HTTPException(
            status_code=404,
            detail="Класс табылган жок"
        )

    return school_class

@router.put("/{class_id}", response_model=ClassOut)
def update_class(
    class_id: int,
    data: ClassCreate,
    current_user: Users = Depends(
        require_roles("DIRECTOR", "DEPUTY")
    ),
    db: Session = Depends(get_db)
):
    school_class = db.query(Classes).filter(
        Classes.id == class_id,
        Classes.school_id == current_user.school_id
    ).first()

    if not school_class:
        raise HTTPException(
            status_code=404,
            detail="Класс табылган жок"
        )

    if data.class_teacher_id is not None:
        teacher = db.query(Users).filter(
            Users.id == data.class_teacher_id,
            Users.school_id == current_user.school_id,
            Users.role.in_(["CLASS_TEACHER", "TEACHER"]),
            Users.is_active == True
        ).first()

        if not teacher:
            raise HTTPException(
                status_code=404,
                detail="Класс жетекчи табылган жок"
            )

    school_class.grade_number = data.grade_number
    school_class.letter = data.letter
    school_class.class_teacher_id = data.class_teacher_id
    school_class.academic_year = data.academic_year

    try:
        db.commit()
        db.refresh(school_class)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Мындай класс мурда түзүлгөн"
        )

    return school_class

@router.delete("/{class_id}")
def delete_class(
    class_id: int,
    current_user: Users = Depends(
        require_roles("DIRECTOR", "DEPUTY")
    ),
    db: Session = Depends(get_db)
):
    school_class = db.query(Classes).filter(
        Classes.id == class_id,
        Classes.school_id == current_user.school_id
    ).first()

    if not school_class:
        raise HTTPException(
            status_code=404,
            detail="Класс табылган жок"
        )

    db.delete(school_class)
    db.commit()

    return {
        "message": "Класс ийгиликтүү өчүрүлдү"
    }

# 4. Класска класс жетекчи дайындоо же алмаштыруу

@router.put("/{class_id}/class-teacher")
def assign_class_teacher(
    class_id: int,
    data: ClassTeacherAssign,
    current_user: Users = Depends(
        require_roles("DIRECTOR", "DEPUTY")
    ),
    db: Session = Depends(get_db)
):
    school_class = db.query(Classes).filter(
        Classes.id == class_id,
        Classes.school_id == current_user.school_id
    ).first()

    if not school_class:
        raise HTTPException(
            status_code=404,
            detail="Класс табылган жок"
        )

    teacher = None

    if data.teacher_id is not None:
        teacher = db.query(Users).filter(
            Users.id == data.teacher_id,
            Users.school_id == current_user.school_id,
            Users.role.in_(["CLASS_TEACHER", "TEACHER"]),
            Users.is_active == True
        ).first()

        if not teacher:
            raise HTTPException(
                status_code=404,
                detail="Мугалим табылган жок"
            )

    school_class.class_teacher_id = (
        teacher.id if teacher else None
    )

    try:
        db.commit()
        db.refresh(school_class)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Класс жетекчини өзгөртүүдө ката кетти"
        )

    return {
        "message": (
            "Класс жетекчи ийгиликтүү дайындалды"
            if teacher else
            "Класс жетекчи класстан алынды"
        ),
        "class_id": school_class.id,
        "class_teacher_id": (
            teacher.id if teacher else None
        ),
        "teacher_name": (
            teacher.full_name if teacher else None
        )
    }
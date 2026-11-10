
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mysite.db.database import get_db
from mysite.db.models import (
    Users,
    Classes,
    Subjects,
    TeacherAssignments
)
from mysite.db.schema import (
    TeacherAssignmentCreate,
    TeacherAssignmentOut
)
from mysite.security.permissions import (
    get_current_user,
    require_roles
)

router = APIRouter(
    prefix="/teacher-assignments",
    tags=["Teacher Assignments"]
)


# 1. Мугалимди класска жана предметке бекитүү
@router.post("/", response_model=TeacherAssignmentOut)
def create_assignment(
    data: TeacherAssignmentCreate,
    db: Session = Depends(get_db),
    current_user: Users = Depends(
        require_roles("DIRECTOR", "DEPUTY")
    )
):

    # Мектепти текшерүү
    if data.school_id != current_user.school_id:
        raise HTTPException(
            status_code=403,
            detail="Бул мектепке уруксат жок"
        )

    # Мугалимди текшерүү
    teacher = db.query(Users).filter(
        Users.id == data.teacher_id,
        Users.school_id == current_user.school_id,
        Users.role == "TEACHER",
        Users.is_active == True
    ).first()

    if not teacher:
        raise HTTPException(
            status_code=404,
            detail="Мугалим табылган жок"
        )

    # Классты текшерүү
    school_class = db.query(Classes).filter(
        Classes.id == data.class_id,
        Classes.school_id == current_user.school_id
    ).first()

    if not school_class:
        raise HTTPException(
            status_code=404,
            detail="Класс табылган жок"
        )

    # Предметти текшерүү
    subject = db.query(Subjects).filter(
        Subjects.id == data.subject_id,
        Subjects.school_id == current_user.school_id
    ).first()

    if not subject:
        raise HTTPException(
            status_code=404,
            detail="Предмет табылган жок"
        )

    # Кайталанган бекитүүнү текшерүү
    existing = db.query(TeacherAssignments).filter(
        TeacherAssignments.teacher_id == data.teacher_id,
        TeacherAssignments.class_id == data.class_id,
        TeacherAssignments.subject_id == data.subject_id,
        TeacherAssignments.school_id == current_user.school_id,
        TeacherAssignments.academic_year == data.academic_year
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail="Бул мугалим буга чейин бекитилген"
        )

    assignment = TeacherAssignments(
        teacher_id=data.teacher_id,
        class_id=data.class_id,
        subject_id=data.subject_id,
        school_id=current_user.school_id,
        academic_year=data.academic_year
    )

    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    return assignment


# 2. Мектептеги бардык бекитүүлөрдү көрүү
@router.get("/", response_model=list[TeacherAssignmentOut])
def get_assignments(
    db: Session = Depends(get_db),
    current_user: Users = Depends(
        require_roles("DIRECTOR", "DEPUTY")
    )
):

    return db.query(TeacherAssignments).filter(
        TeacherAssignments.school_id == current_user.school_id
    ).all()



@router.get("/teacher/{teacher_id}")
def get_teacher_assignments(
    teacher_id: int,
    db: Session = Depends(get_db),
    current_user: Users = Depends(get_current_user)
):

    if current_user.role == "TEACHER":
        if current_user.id != teacher_id:
            raise HTTPException(
                status_code=403,
                detail="Башка мугалимдин маалыматтарына уруксат жок"
            )

    elif current_user.role not in ["DIRECTOR", "DEPUTY"]:
        raise HTTPException(
            status_code=403,
            detail="Уруксат жок"
        )

    teacher = db.query(Users).filter(
        Users.id == teacher_id,
        Users.school_id == current_user.school_id,
        Users.role == "TEACHER"
    ).first()

    if not teacher:
        raise HTTPException(
            status_code=404,
            detail="Мугалим табылган жок"
        )

    return db.query(TeacherAssignments).filter(
        TeacherAssignments.teacher_id == teacher_id,
        TeacherAssignments.school_id == current_user.school_id
    ).all()


@router.delete("/{assignment_id}")
def delete_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    current_user: Users = Depends(
        require_roles("DIRECTOR", "DEPUTY")
    )
):

    assignment = db.query(TeacherAssignments).filter(
        TeacherAssignments.id == assignment_id,
        TeacherAssignments.school_id == current_user.school_id
    ).first()

    if not assignment:
        raise HTTPException(
            status_code=404,
            detail="Бекитүү табылган жок"
        )

    db.delete(assignment)
    db.commit()

    return {
        "message": "Мугалимдин бекитүүсү өчүрүлдү"
    }

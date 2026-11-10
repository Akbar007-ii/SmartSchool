
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from mysite.db.database import get_db
from mysite.db.models import Subjects, Users
from mysite.db.schema import SubjectCreate, SubjectOut
from mysite.security.permissions import (
    get_current_user,
    require_roles
)

router = APIRouter(
    prefix="/subjects",
    tags=["Subjects"]
)


# Мектептин предметтерин көрүү
@router.get("/", response_model=list[SubjectOut])
def get_subjects(
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    subjects = db.query(Subjects).filter(
        Subjects.school_id == current_user.school_id
    ).order_by(Subjects.name).all()

    return subjects


# Жаңы предмет кошуу
@router.post("/", response_model=SubjectOut)
def create_subject(
    data: SubjectCreate,
    current_user: Users = Depends(
        require_roles("DIRECTOR", "DEPUTY")
    ),
    db: Session = Depends(get_db)
):
    new_subject = Subjects(
        name=data.name,
        code=data.code,
        school_id=current_user.school_id
    )

    db.add(new_subject)

    try:
        db.commit()
        db.refresh(new_subject)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Бул предмет мурда кошулган"
        )

    return new_subject


# Белгилүү бир предметти көрүү
@router.get("/{subject_id}", response_model=SubjectOut)
def get_subject(
    subject_id: int,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    subject = db.query(Subjects).filter(
        Subjects.id == subject_id,
        Subjects.school_id == current_user.school_id
    ).first()

    if not subject:
        raise HTTPException(
            status_code=404,
            detail="Предмет табылган жок"
        )

    return subject


from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from mysite.db.database import get_db
from mysite.db.models import Schools, Users
from mysite.db.schema import SchoolUpdate, SchoolOut
from mysite.security.permissions import (
    get_current_user,
    require_roles
)

router = APIRouter(
    prefix="/schools",
    tags=["Schools"]
)


# 1. Өз мектебинин маалыматын көрүү
@router.get("/me", response_model=SchoolOut)
def get_my_school(
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    school = db.query(Schools).filter(
        Schools.id == current_user.school_id
    ).first()

    if not school:
        raise HTTPException(
            status_code=404,
            detail="Мектеп табылган жок"
        )

    return school


# 2. Мектептин маалыматын өзгөртүү
@router.put("/me", response_model=SchoolOut)
def update_my_school(
    data: SchoolUpdate,
    current_user: Users = Depends(
        require_roles("DIRECTOR", "DEPUTY")
    ),
    db: Session = Depends(get_db)
):
    school = db.query(Schools).filter(
        Schools.id == current_user.school_id
    ).first()

    if not school:
        raise HTTPException(
            status_code=404,
            detail="Мектеп табылган жок"
        )

    update_data = data.model_dump(exclude_unset=True)

    if not update_data:
        raise HTTPException(
            status_code=400,
            detail="Өзгөртүү үчүн маалымат берилген жок"
        )

    for key, value in update_data.items():
        setattr(school, key, value)

    try:
        db.commit()
        db.refresh(school)

    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Мектептин маалыматын жаңыртууда ката кетти"
        )

    return school
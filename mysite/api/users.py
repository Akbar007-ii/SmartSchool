from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mysite.db.database import get_db
from mysite.db.models import Users
from mysite.security.permissions import (
    get_current_user,
    get_school_user
)

router = APIRouter(
    prefix="/users",
    tags=["Users"]
)


@router.get("/{user_id}")
def get_user(
    user_id: int,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = get_school_user(
        user_id=user_id,
        current_user=current_user,
        db=db
    )

    return {
        "id": user.id,
        "full_name": user.full_name,
        "role": user.role,
        "school_id": user.school_id
    }


import secrets
import string

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from mysite.db.database import get_db
from mysite.db.models import Users, ParentStudents
from mysite.db.schema import ParentRegister, ParentAddChild
from mysite.security.hashing import hash_password, verify_password
from mysite.security.jwt import create_access_token
from mysite.security import login_limit
from mysite.security.permissions import (
    get_current_user,
    require_roles
)

# Окуучуга эң көп эки ата-эне (апа жана ата) байланат.
MAX_PARENTS_PER_STUDENT = 2


def ensure_can_link(db: Session, parent_id, student_id: int) -> None:
    """Ушул ата-эне мурда байланганбы жана окуучунун ата-энелеринин саны толгонбу."""
    links = db.query(ParentStudents).filter(
        ParentStudents.student_id == student_id
    ).all()

    if parent_id is not None and any(link.parent_id == parent_id for link in links):
        raise HTTPException(
            status_code=400,
            detail="Бул окуучу сиздин аккаунтуңузга мурда байланган"
        )

    if len(links) >= MAX_PARENTS_PER_STUDENT:
        raise HTTPException(
            status_code=400,
            detail="Бул окуучуга эки ата-эне байланган — дагы кошууга болбойт"
        )


router = APIRouter(
    prefix="/parents",
    tags=["Parents"]
)


def generate_password(length=12):
    alphabet = string.ascii_letters + string.digits
    return ''.join(
        secrets.choice(alphabet)
        for _ in range(length)
    )


def get_parent_token(parent):
    return create_access_token({
        "sub": str(parent.id),
        "school_id": parent.school_id,
        "role": parent.role
    })


# 1. Ата-энени каттоо жана биринчи баласын кошуу
@router.post("/register")
def register_parent(
    data: ParentRegister,
    request: Request,
    db: Session = Depends(get_db)
):
    if db.query(Users).filter(
        Users.email == data.email
    ).first():
        raise HTTPException(
            status_code=400,
            detail="Бул почта мурда катталган"
        )

    login_limit.ensure_not_blocked(data.student_email, login_limit.client_ip(request))

    student = db.query(Users).filter(
        Users.email == data.student_email,
        Users.role == "STUDENT",
        Users.is_active.is_(True)
    ).first()

    if not student:
        raise HTTPException(
            status_code=404,
            detail="Окуучу табылган жок"
        )

    if not student.is_temp_password:
        raise HTTPException(
            status_code=400,
            detail="Окуучунун убактылуу паролу колдонулган"
        )

    if not verify_password(
        data.student_password,
        student.hashed_password
    ):
        login_limit.record_failure(data.student_email, login_limit.client_ip(request))
        raise HTTPException(
            status_code=400,
            detail="Окуучунун почтасы же паролу туура эмес"
        )

    ensure_can_link(db, None, student.id)

    try:
        parent = Users(
            email=data.email,
            full_name=data.full_name.strip(),
            role="PARENT",
            hashed_password=hash_password(data.password),
            is_temp_password=False,
            school_id=student.school_id,
            is_active=True
        )

        db.add(parent)
        db.flush()

        link = ParentStudents(
            parent_id=parent.id,
            student_id=student.id
        )

        db.add(link)
        db.commit()
        db.refresh(parent)

        return {
            "message": "Ата-эне ийгиликтүү катталды",
            "parent_id": parent.id,
            "full_name": parent.full_name,
            "student": student.full_name,
            "access_token": get_parent_token(parent),
            "token_type": "bearer"
        }

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Бул окуучу мурда байланыштырылган же почта катталган"
        )

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Каттоодо ката кетти"
        )


# 2. Кийинки баланы кошуу
@router.post("/add-child")
def add_child(
    data: ParentAddChild,
    request: Request,
    current_user: Users = Depends(
        require_roles("PARENT")
    ),
    db: Session = Depends(get_db)
):
    login_limit.ensure_not_blocked(data.student_email, login_limit.client_ip(request))

    student = db.query(Users).filter(
        Users.email == data.student_email,
        Users.role == "STUDENT",
        Users.school_id == current_user.school_id,
        Users.is_active.is_(True)
    ).first()

    if not student:
        raise HTTPException(
            status_code=404,
            detail="Окуучу табылган жок"
        )

    if not student.is_temp_password:
        raise HTTPException(
            status_code=400,
            detail="Окуучунун убактылуу паролу колдонулган"
        )

    if not verify_password(
        data.student_password,
        student.hashed_password
    ):
        login_limit.record_failure(data.student_email, login_limit.client_ip(request))
        raise HTTPException(
            status_code=400,
            detail="Окуучунун почтасы же паролу туура эмес"
        )

    ensure_can_link(db, current_user.id, student.id)

    try:
        link = ParentStudents(
            parent_id=current_user.id,
            student_id=student.id
        )

        db.add(link)
        db.commit()

        return {
            "message": "Бала ийгиликтүү кошулду",
            "student_id": student.id,
            "full_name": student.full_name
        }

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Окуучу мурда байланыштырылган"
        )


# 3. Ата-эненин балдары
@router.get("/my-children")
def get_my_children(
    current_user: Users = Depends(
        require_roles("PARENT")
    ),
    db: Session = Depends(get_db)
):
    links = db.query(ParentStudents).filter(
        ParentStudents.parent_id == current_user.id
    ).all()

    children = []

    for link in links:
        student = db.query(Users).filter(
            Users.id == link.student_id,
            Users.role == "STUDENT"
        ).first()

        if student:
            children.append({
                "id": student.id,
                "email": student.email,
                "full_name": student.full_name,
                "is_active": student.is_active
            })

    return {
        "parent_id": current_user.id,
        "parent_name": current_user.full_name,
        "total_children": len(children),
        "children": children
    }

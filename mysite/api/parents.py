
import secrets
import string

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from mysite.db.database import get_db
from mysite.db.models import Users, ParentStudents
from mysite.db.schema import ParentRegister, ParentAddChild
from mysite.security.hashing import hash_password
from mysite.security.jwt import create_access_token, password_fingerprint
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


def find_student_by_code(db: Session, code: str, request: Request, school_id=None) -> Users:
    """Окуучуну ата-эне коду боюнча табат. Кодду тандап табууга каршы IP боюнча чек коюлат."""
    ip = login_limit.client_ip(request)
    login_limit.ensure_not_blocked("parent-code", ip)

    query = db.query(Users).filter(
        Users.parent_code == code,
        Users.role == "STUDENT",
        Users.is_active.is_(True)
    )
    if school_id is not None:
        query = query.filter(Users.school_id == school_id)
    student = query.first()

    if not student:
        login_limit.record_failure("parent-code", ip)
        raise HTTPException(
            status_code=404,
            detail="Мындай код менен окуучу табылган жок"
        )
    return student


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
        "role": parent.role,
        "pwd": password_fingerprint(parent.hashed_password),
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

    student = find_student_by_code(db, data.student_code, request)

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
    student = find_student_by_code(db, data.student_code, request, current_user.school_id)

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

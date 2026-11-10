
import secrets
import string

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from mysite.db.database import get_db
from mysite.db.models import Users, ParentStudents
from mysite.db.schema import ParentRegister, ParentAddChild
from mysite.security.hashing import hash_password, verify_password
from mysite.security.jwt import create_access_token
from mysite.security.permissions import (
    get_current_user,
    require_roles
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
    db: Session = Depends(get_db)
):
    if not data.inn.isdigit() or len(data.inn) != 14:
        raise HTTPException(
            status_code=400,
            detail="ИНН 14 цифра болушу керек"
        )

    if db.query(Users).filter(
        Users.inn == data.inn
    ).first():
        raise HTTPException(
            status_code=400,
            detail="Бул ИНН мурда катталган"
        )

    student = db.query(Users).filter(
        Users.inn == data.student_inn,
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
        raise HTTPException(
            status_code=400,
            detail="Окуучунун ИННи же паролу туура эмес"
        )

    existing_link = db.query(ParentStudents).filter(
        ParentStudents.student_id == student.id
    ).first()

    if existing_link:
        raise HTTPException(
            status_code=400,
            detail="Бул окуучу башка ата-энеге байланышкан"
        )

    try:
        parent = Users(
            inn=data.inn,
            full_name=data.full_name.strip(),
            phone=data.phone,
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
            detail="Бул окуучу мурда байланыштырылган же ИНН катталган"
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
    current_user: Users = Depends(
        require_roles("PARENT")
    ),
    db: Session = Depends(get_db)
):
    student = db.query(Users).filter(
        Users.inn == data.student_inn,
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
        raise HTTPException(
            status_code=400,
            detail="Окуучунун ИННи же паролу туура эмес"
        )

    existing = db.query(ParentStudents).filter(
        ParentStudents.student_id == student.id
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail="Бул окуучу башка ата-энеге байланышкан"
        )

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
                "inn": student.inn,
                "full_name": student.full_name,
                "phone": student.phone,
                "is_active": student.is_active
            })

    return {
        "parent_id": current_user.id,
        "parent_name": current_user.full_name,
        "total_children": len(children),
        "children": children
    }

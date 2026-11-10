
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from mysite.db.database import get_db
from mysite.db.models import Users, ParentStudents, Schools
from mysite.security.jwt import verify_access_token


oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/login"
)


# =====================================================
# 1. CURRENT USER
# =====================================================

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> Users:

    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Авторизация талап кылынат",
        headers={"WWW-Authenticate": "Bearer"}
    )

    payload = verify_access_token(token)

    if payload is None:
        raise credentials_error

    try:
        user_id = int(payload.get("sub"))
        token_school_id = int(payload.get("school_id"))
    except (ValueError, TypeError):
        raise credentials_error

    token_role = payload.get("role")

    if not token_role:
        raise credentials_error

    user = db.query(Users).filter(
        Users.id == user_id,
        Users.is_active.is_(True)
    ).first()

    if user is None:
        raise credentials_error

    # JWT жана база маалыматтарын салыштыруу
    if user.school_id != token_school_id:
        raise credentials_error

    if user.role != token_role:
        raise credentials_error

    # SYSTEM_ADMINден башка бардык колдонуучулар
    # активдүү мектепке гана кире алышат
    if user.role != "SYSTEM_ADMIN":

        school = db.query(Schools).filter(
            Schools.id == user.school_id
        ).first()

        if school is None or not school.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Мектеп убактылуу жабылган"
            )

    return user


# =====================================================
# 2. ROLE CHECK
# =====================================================

def require_roles(*allowed_roles):

    def role_checker(
        current_user: Users = Depends(get_current_user)
    ):

        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Бул аракетке уруксатыңыз жок"
            )

        return current_user

    return role_checker


# =====================================================
# 3. SCHOOL ACCESS
# =====================================================

def check_school_access(
    school_id: int,
    current_user: Users
):

    if current_user.role == "SYSTEM_ADMIN":
        return True

    if current_user.school_id != school_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Бул мектептин маалыматтарына кирүүгө уруксат жок"
        )

    return True


# =====================================================
# 4. GET USER FROM SAME SCHOOL
# =====================================================

def get_school_user(
    user_id: int,
    current_user: Users,
    db: Session
) -> Users:

    query = db.query(Users).filter(
        Users.id == user_id
    )

    if current_user.role != "SYSTEM_ADMIN":
        query = query.filter(
            Users.school_id == current_user.school_id
        )

    user = query.first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Колдонуучу табылган жок"
        )

    return user


# =====================================================
# 5. PARENT CHILD ACCESS
# =====================================================

def get_parent_child(
    student_id: int,
    current_user: Users,
    db: Session
) -> Users:

    if current_user.role != "PARENT":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Бул аракет ата-энелер үчүн гана"
        )

    link = db.query(ParentStudents).filter(
        ParentStudents.parent_id == current_user.id,
        ParentStudents.student_id == student_id
    ).first()

    if link is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Бул окуучу сиздин аккаунтуңузга байланышкан эмес"
        )

    student = db.query(Users).filter(
        Users.id == student_id,
        Users.school_id == current_user.school_id,
        Users.role == "STUDENT",
        Users.is_active.is_(True)
    ).first()

    if student is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Окуучу табылган жок"
        )

    return student


# =====================================================
# 6. ROLE DEPENDENCIES
# =====================================================

system_admin_required = require_roles(
    "SYSTEM_ADMIN"
)

director_required = require_roles(
    "DIRECTOR"
)

admin_required = require_roles(
    "DIRECTOR",
    "DEPUTY"
)

teacher_required = require_roles(
    "DIRECTOR",
    "DEPUTY",
    "CLASS_TEACHER",
    "TEACHER"
)

class_teacher_required = require_roles(
    "CLASS_TEACHER"
)

student_required = require_roles(
    "STUDENT"
)

parent_required = require_roles(
    "PARENT"
)
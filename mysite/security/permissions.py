
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from mysite.db.database import get_db
from mysite.db.models import Users
from mysite.security.jwt import verify_access_token


oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/login"
)

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):

    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Авторизация талап кылынат",
        headers={"WWW-Authenticate": "Bearer"}
    )

    payload = verify_access_token(token)

    if payload is None:
        raise credentials_error

    user_id = payload.get("sub")

    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        raise credentials_error

    user = db.query(Users).filter(
        Users.id == user_id,
        Users.is_active.is_(True)
    ).first()

    if user is None:
        raise credentials_error

    return user


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


from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

# Мисал үчүн модель жана ролдор декоратору (сиздин долбоордогудай импорттолот)
# from .models import Users
# from .security import require_roles

def check_school_access(
    school_id: int,
    current_user: Users
):

    if current_user.school_id != school_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Бул мектептин маалыматтарына кирүүгө уруксат жок"
        )
    return True


def get_school_user(
    user_id: int,
    current_user: Users,
    db: Session
) -> Users:
    user = db.query(Users).filter(
        Users.id == user_id,
        Users.school_id == current_user.school_id
    ).first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Колдонуучу табылган жок"
        )

    return user



director_required = require_roles("DIRECTOR")

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

student_required = require_roles("STUDENT")

parent_required = require_roles("PARENT")

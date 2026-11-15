"""Мектеп жетекчилеринин (директор, завуч) аккаунттарын түзүү."""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from mysite.db.models import Users
from mysite.services.passwords import decrypt_temp_password, set_temp_password


def create_school_admin(
    db: Session,
    school_id: int,
    inn: str,
    full_name: str,
    role: str,
    phone: str | None = None,
) -> tuple[Users, str]:
    """Директор же завуч түзөт; убактылуу сыр сөздү кайтарат (commit кылбайт)."""
    if role not in ("DIRECTOR", "DEPUTY"):
        raise HTTPException(status_code=400, detail="Ролу DIRECTOR же DEPUTY болушу керек")

    if db.query(Users.id).filter(Users.inn == inn).first():
        raise HTTPException(status_code=400, detail=f"ИНН {inn} мурда катталган")

    user = Users(
        inn=inn,
        full_name=full_name.strip(),
        phone=phone,
        role=role,
        hashed_password="",
        school_id=school_id,
        is_active=True,
    )
    password = set_temp_password(user)
    db.add(user)
    db.flush()
    return user, password


def admin_row(user: Users) -> dict:
    """Жетекчинин маалыматы; сыр сөзүн алмаштыра элек болсо убактылуу сыр сөзү менен."""
    return {
        "id": user.id,
        "inn": user.inn,
        "full_name": user.full_name,
        "phone": user.phone,
        "role": user.role,
        "is_active": user.is_active,
        "is_temp_password": user.is_temp_password,
        "temporary_password": (
            decrypt_temp_password(user.temp_password_encrypted)
            if user.is_temp_password else None
        ),
        "created_at": user.created_at,
    }

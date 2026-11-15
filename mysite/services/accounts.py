"""Мектеп жетекчилеринин (директор, завуч) аккаунттарын түзүү."""
from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from mysite.db.models import Users
from mysite.services.passwords import decrypt_temp_password, set_temp_password


# Мектепте бир гана директор жана эң көп 5 завуч болот.
# Активдүү аккаунттар гана саналат: өчүрүлгөндүн ордуна жаңысын кошсо болот.
MAX_SCHOOL_ADMINS = {"DIRECTOR": 1, "DEPUTY": 5}


def ensure_admin_limit(db: Session, school_id: int, role: str) -> None:
    """Ролдун чеги толуп калса 400 кайтарат (кошуудан же кайра күйгүзүүдөн мурда)."""
    limit = MAX_SCHOOL_ADMINS.get(role)
    if limit is None:
        return

    active_count = db.query(func.count(Users.id)).filter(
        Users.school_id == school_id,
        Users.role == role,
        Users.is_active.is_(True),
    ).scalar() or 0

    if active_count >= limit:
        if role == "DIRECTOR":
            detail = "Мектепте директор мурда дайындалган. Жаңысын кошуу үчүн учурдагы директорду өчүрүңүз"
        else:
            detail = f"Мектепте завучтар эң көп {limit} болот. Жаңысын кошуу үчүн алардын бирин өчүрүңүз"
        raise HTTPException(status_code=400, detail=detail)


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

    ensure_admin_limit(db, school_id, role)

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

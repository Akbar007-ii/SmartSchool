import hashlib
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from mysite.db.database import get_db
from mysite.db.models import Users
from mysite.db.schema import ForgotPassword, LoginRequest, FirstLoginChange, ResetPassword, TokenResponse

from mysite.security.hashing import verify_password,hash_password

from mysite.security.jwt import ALGORITHM, SECRET_KEY, create_access_token, password_fingerprint
from mysite.services.mailer import FRONTEND_URL, send_email
from mysite.security import login_limit
from mysite.security.permissions import get_current_user


router = APIRouter(prefix="/auth",tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, request: Request, db: Session = Depends(get_db)):
    ip = login_limit.client_ip(request)
    # Сыр сөздү тандап табууга каршы: ийгиликсиз аракеттер чектелет (429)
    login_limit.ensure_not_blocked(data.email, ip)

    user = db.query(Users).filter(Users.email == data.email).first()
    if not user or not verify_password(data.password, user.hashed_password):
        login_limit.record_failure(data.email, ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,detail="Почта же сыр сөз туура эмес")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,detail="Аккаунт убактылуу жабылган")
    login_limit.reset(data.email)

    access_token = create_access_token({
        "sub": str(user.id),
        "school_id": user.school_id,
        "role": user.role,
        "pwd": password_fingerprint(user.hashed_password),
    })

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "requires_password_change": user.is_temp_password
    }


@router.post("/first-login-change",response_model=TokenResponse)
def first_login_change(data: FirstLoginChange,current_user: Users = Depends(get_current_user),db: Session = Depends(get_db)):
    if not current_user.is_temp_password:
        raise HTTPException(status_code=400,detail="Сыр сөз мурда эле өзгөртүлгөн")
    if not verify_password(data.current_password,current_user.hashed_password):
        raise HTTPException(status_code=400,detail="Учурдагы сыр сөз туура эмес")
    if verify_password(data.new_password,current_user.hashed_password):
        raise HTTPException(status_code=400,detail="Жаңы сыр сөз эски сыр сөздөн айырмаланышы керек")
    if len(data.new_password) < 8:
        raise HTTPException(
            status_code=400,
            detail="Жаңы сыр сөз кеминде 8 белгиден турушу керек"
        )
    current_user.hashed_password = hash_password(data.new_password)
    current_user.is_temp_password = False
    current_user.temp_password_encrypted = None
    db.commit()
    db.refresh(current_user)
    access_token = create_access_token({
        "sub": str(current_user.id),
        "school_id": current_user.school_id,
        "role": current_user.role,
        "pwd": password_fingerprint(current_user.hashed_password),
    })

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "requires_password_change": False
    }



# =====================================================
# Сыр сөздү унутуп калса: почтага шилтеме жөнөтүү
# =====================================================

RESET_TOKEN_MINUTES = 30


def _password_fingerprint(user: Users) -> str:
    # Сыр сөз алмашканда шилтеме жараксыз болот (бир жолу гана иштейт)
    return password_fingerprint(user.hashed_password)


def create_reset_token(user: Users) -> str:
    # "sub" атайын коюлган жок: бул токен менен API'ге кирүүгө болбойт
    return pyjwt.encode(
        {
            "reset_uid": user.id,
            "pwd": _password_fingerprint(user),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_MINUTES),
        },
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


@router.post("/forgot-password")
def forgot_password(data: ForgotPassword, request: Request, db: Session = Depends(get_db)):
    ip = login_limit.client_ip(request)
    login_limit.ensure_not_blocked(f"reset:{data.email}", ip)
    # Ар бир суроо эсептелет: бир почтага каттарды көп жөнөтүүгө болбойт
    login_limit.record_failure(f"reset:{data.email}", ip)

    user = db.query(Users).filter(Users.email == data.email, Users.is_active.is_(True)).first()
    if user:
        link = f"{FRONTEND_URL}/reset-password?token={create_reset_token(user)}"
        send_email(
            user.email,
            "Smart School: сыр сөздү калыбына келтирүү",
            f"Саламатсызбы, {user.full_name}!\n\n"
            f"Жаңы сыр сөз коюу үчүн шилтемени ачыңыз ({RESET_TOKEN_MINUTES} мүнөт иштейт):\n{link}\n\n"
            "Эгер сиз сурабасаңыз, бул катка көңүл бурбаңыз.",
        )

    # Почта базада барбы-жокпу — жооп бирдей (бөтөн адам почталарды текшере албасын)
    return {"message": "Эгер бул почта катталган болсо, ага шилтеме жөнөтүлдү"}


@router.post("/reset-password")
def reset_password(data: ResetPassword, db: Session = Depends(get_db)):
    invalid = HTTPException(status_code=400, detail="Шилтеме жараксыз же мөөнөтү өтүп кеткен")
    try:
        payload = pyjwt.decode(data.token, SECRET_KEY, algorithms=[ALGORITHM])
    except pyjwt.PyJWTError:
        raise invalid

    user = db.query(Users).filter(Users.id == payload.get("reset_uid"), Users.is_active.is_(True)).first()
    if not user or payload.get("pwd") != _password_fingerprint(user):
        raise invalid

    user.hashed_password = hash_password(data.new_password)
    user.is_temp_password = False
    user.temp_password_encrypted = None
    db.commit()
    login_limit.reset(user.email)
    return {"message": "Сыр сөз жаңыртылды"}

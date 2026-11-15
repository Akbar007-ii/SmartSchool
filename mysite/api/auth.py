from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from mysite.db.database import get_db
from mysite.db.models import Users
from mysite.db.schema import LoginRequest, FirstLoginChange, TokenResponse

from mysite.security.hashing import verify_password,hash_password

from mysite.security.jwt import create_access_token
from mysite.security import login_limit
from mysite.security.permissions import get_current_user


router = APIRouter(prefix="/auth",tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, request: Request, db: Session = Depends(get_db)):
    ip = login_limit.client_ip(request)
    # Сыр сөздү тандап табууга каршы: ийгиликсиз аракеттер чектелет (429)
    login_limit.ensure_not_blocked(data.inn, ip)

    user = db.query(Users).filter(Users.inn == data.inn).first()
    if not user or not verify_password(data.password, user.hashed_password):
        login_limit.record_failure(data.inn, ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,detail="ИНН же сыр сөз туура эмес")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,detail="Аккаунт убактылуу жабылган")
    login_limit.reset(data.inn)

    access_token = create_access_token({
        "sub": str(user.id),
        "school_id": user.school_id,
        "role": user.role
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
        "role": current_user.role
    })

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "requires_password_change": False
    }


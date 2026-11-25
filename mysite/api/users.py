
import secrets
import string

from io import BytesIO

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    File
)
from mysite.db.schema import TeacherCreate,TeacherCreatedOut,normalize_email
from mysite.services.accounts import send_welcome_email

from fastapi.responses import StreamingResponse

from sqlalchemy.orm import Session

from openpyxl import load_workbook
from openpyxl import Workbook

from mysite.db.database import get_db
from mysite.db.models import Users
from mysite.security.permissions import (
    get_current_user,
    get_school_user,
    require_roles
)
from mysite.security.hashing import hash_password
from mysite.services.passwords import encrypt_temp_password, set_temp_password
from mysite.services.text_checks import validate_person_name


router = APIRouter(
    prefix="/users",
    tags=["Users"]
)


# Убактылуу сыр сөз түзүү
def generate_password(length=10):
    characters = string.ascii_letters + string.digits + "!@#$"
    return ''.join(
        secrets.choice(characters)
        for _ in range(length)
    )


# Бир колдонуучуну көрүү
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


from mysite.db.schema import TeacherCreate


@router.post("/create-teacher", response_model=TeacherCreatedOut)
def create_teacher(
    data: TeacherCreate,
    current_user: Users = Depends(
        require_roles("DIRECTOR", "DEPUTY")
    ),
    db: Session = Depends(get_db)
):

    # Почта мурда колдонулганбы?
    existing_user = db.query(Users).filter(
        Users.email == data.email
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Бул почта мурда катталган"
        )

    # Убактылуу сыр сөз
    temporary_password = generate_password()

    teacher = Users(
        email=data.email,
        full_name=data.full_name,
        role="TEACHER",
        hashed_password=hash_password(temporary_password),
        temp_password_encrypted=encrypt_temp_password(temporary_password),
        is_temp_password=True,
        school_id=current_user.school_id,
        is_active=True
    )

    db.add(teacher)
    db.commit()
    db.refresh(teacher)
    send_welcome_email(teacher.email, teacher.full_name, temporary_password)

    return {
        "id": teacher.id,
        "email": teacher.email,
        "full_name": teacher.full_name,
        "temporary_password": temporary_password,
        "role": teacher.role,
        "school_id": teacher.school_id
    }



# Excel аркылуу мугалимдерди жапырт жүктөө
@router.post("/import-excel")
async def import_teachers_excel(
    file: UploadFile = File(...),
    current_user: Users = Depends(
        require_roles("DIRECTOR", "DEPUTY")
    ),
    db: Session = Depends(get_db)
):

    if not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(
            status_code=400,
            detail="Excel файлы .xlsx форматында болушу керек"
        )

    content = await file.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Файл 5 МБдан ашпашы керек")

    try:
        workbook = load_workbook(
            BytesIO(content),
            read_only=True,
            data_only=True
        )
        sheet = workbook.active
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Excel файлын окуу мүмкүн болгон жок"
        )

    created_teachers = []
    errors = []

    # Биринчи сап: Почта | Аты-жөнү
    for row_number, row in enumerate(
        sheet.iter_rows(min_row=2, values_only=True),
        start=2
    ):

        if not row or all(value is None for value in row):
            continue

        full_name = str(row[1]).strip() if len(row) > 1 and row[1] else ""

        try:
            email = normalize_email(str(row[0] or ""))
        except ValueError as error:
            errors.append({"row": row_number, "error": str(error)})
            continue

        if len(full_name) < 3:
            errors.append({
                "row": row_number,
                "error": "Аты-жөнү туура эмес"
            })
            continue

        try:
            full_name = validate_person_name(full_name)
        except ValueError as error:
            errors.append({"row": row_number, "error": str(error)})
            continue

        # Мурда кошулганбы?
        existing_user = db.query(Users).filter(
            Users.email == email
        ).first()

        if existing_user:
            errors.append({
                "row": row_number,
                "error": "Бул почта мурда катталган"
            })
            continue

        # Сыр сөз түзүү
        temporary_password = generate_password()

        teacher = Users(
            email=email,
            full_name=full_name,
            role="TEACHER",
            hashed_password=hash_password(temporary_password),
            temp_password_encrypted=encrypt_temp_password(temporary_password),
            is_temp_password=True,
            school_id=current_user.school_id,
            is_active=True
        )

        db.add(teacher)

        created_teachers.append({
            "email": email,
            "full_name": full_name,
            "password": temporary_password
        })

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Мугалимдерди базага сактоодо ката кетти"
        )

    # Натыйжаны Excel кылып түзүү
    result_workbook = Workbook()
    result_sheet = result_workbook.active
    result_sheet.title = "Мугалимдер"

    result_sheet.append([
        "Почта",
        "Аты-жөнү",
        "Убактылуу сыр сөз"
    ])

    for teacher in created_teachers:
        result_sheet.append([
            teacher["email"],
            teacher["full_name"],
            teacher["password"]
        ])

    output = BytesIO()
    result_workbook.save(output)
    output.seek(0)

    return StreamingResponse(
        output,
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition":
            'attachment; filename="teachers_passwords.xlsx"'
        }
    )

@router.post("/{user_id}/reset-password")
def reset_user_password(
    user_id: int,
    current_user: Users = Depends(
        require_roles("DIRECTOR", "DEPUTY")
    ),
    db: Session = Depends(get_db)
):
    user = db.query(Users).filter(
        Users.id == user_id,
        Users.school_id == current_user.school_id
    ).first()

    if not user:
        raise HTTPException(
            status_code=404,
            detail="Колдонуучу табылган жок"
        )

    if user.role not in ["TEACHER", "CLASS_TEACHER"]:
        raise HTTPException(
            status_code=400,
            detail="Бул колдонуучунун сыр сөзүн бул API аркылуу өзгөртүүгө болбойт"
        )

    temporary_password = generate_password()

    try:
        user.hashed_password = hash_password(
            temporary_password
        )
        user.is_temp_password = True
        user.temp_password_encrypted = encrypt_temp_password(
            temporary_password
        )

        db.commit()

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Сыр сөздү өзгөртүүдө ката кетти"
        )

    return {
        "message": "Сыр сөз ийгиликтүү жаңыртылды",
        "user_id": user.id,
        "full_name": user.full_name,
        "temporary_password": temporary_password
    }


import secrets
import string
from io import BytesIO

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from openpyxl import load_workbook

from mysite.db.database import get_db
from mysite.db.models import Users
from mysite.security.permissions import require_roles
from mysite.security.hashing import hash_password


router = APIRouter(
    prefix="/teachers",
    tags=["Teacher Import"]
)


def generate_password(length=10):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


@router.post("/import-excel")
def import_teachers_excel(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: Users = Depends(
        require_roles("DIRECTOR", "DEPUTY")
    )
):

    # Файлдын форматын текшерүү
    if not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(
            status_code=400,
            detail="Excel файлы .xlsx форматында болушу керек"
        )

    try:
        content = file.file.read()

        if len(content) > 5 * 1024 * 1024:
            raise HTTPException(
                status_code=400,
                detail="Файлдын көлөмү 5 MB ашпашы керек"
            )

        workbook = load_workbook(
            BytesIO(content),
            read_only=True,
            data_only=True
        )

        sheet = workbook.active

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Excel файлын окуу мүмкүн болгон жок"
        )

    # Башкы саптарды текшерүү
    headers = [
        str(cell.value).strip().lower() if cell.value is not None else ""
        for cell in sheet[1]
    ]

    required_headers = ["инн", "толук аты-жөнү", "телефон"]

    if headers[:3] != required_headers:
        workbook.close()
        raise HTTPException(
            status_code=400,
            detail="Excel мамычалары: ИНН, Толук аты-жөнү, Телефон болушу керек"
        )

    added_teachers = []
    errors = []
    seen_inns = set()

    try:
        for row_number, row in enumerate(
            sheet.iter_rows(min_row=2, max_col=3, values_only=True),
            start=2
        ):

            inn_value, full_name, phone = row

            if all(value is None for value in row):
                continue

            # ИНН текшерүү
            inn = str(inn_value).strip() if inn_value is not None else ""

            if not inn.isdigit() or len(inn) != 14:
                errors.append({
                    "row": row_number,
                    "error": "ИНН 14 цифра болушу керек"
                })
                continue

            if inn in seen_inns:
                errors.append({
                    "row": row_number,
                    "error": "Excel ичинде ИНН кайталанды"
                })
                continue

            seen_inns.add(inn)

            # Аты-жөнүн текшерүү
            if not full_name or len(str(full_name).strip()) < 3:
                errors.append({
                    "row": row_number,
                    "error": "Аты-жөнү туура эмес"
                })
                continue

            existing_user = db.query(Users).filter(
                Users.inn == inn
            ).first()

            if existing_user:
                errors.append({
                    "row": row_number,
                    "error": "Бул ИНН мурда катталган"
                })
                continue

            # Убактылуу сыр сөз
            temporary_password = generate_password()

            teacher = Users(
                inn=inn,
                full_name=str(full_name).strip(),
                role="TEACHER",
                hashed_password=hash_password(temporary_password),
                is_temp_password=True,
                phone=str(phone).strip() if phone else None,
                school_id=current_user.school_id,
                is_active=True
            )

            db.add(teacher)

            added_teachers.append({
                "inn": inn,
                "full_name": teacher.full_name,
                "temporary_password": temporary_password
            })

        db.commit()

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Мугалимдерди базага сактоодо ката кетти"
        )
    finally:
        workbook.close()

    return {
        "message": "Excel жүктөө аяктады",
        "total_added": len(added_teachers),
        "total_errors": len(errors),
        "added_teachers": added_teachers,
        "errors": errors
    }


import secrets
import string
from io import BytesIO

from fastapi import (
    APIRouter,
    Depends,
    UploadFile,
    File,
    HTTPException
)
from sqlalchemy.orm import Session
from openpyxl import load_workbook

from mysite.db.database import get_db
from mysite.db.models import (
    Users,
    Classes,
    StudentEnrollments
)
from mysite.security.permissions import require_roles
from mysite.security.hashing import hash_password
from mysite.services.passwords import encrypt_temp_password, set_temp_password


router = APIRouter(
    prefix="/students",
    tags=["Student Import"]
)


def generate_password(length=10):
    alphabet = string.ascii_letters + string.digits
    return ''.join(
        secrets.choice(alphabet)
        for _ in range(length)
    )


@router.post("/import-excel/{class_id}")
def import_students_excel(
    class_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: Users = Depends(
        require_roles("DIRECTOR", "DEPUTY")
    )
):

    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(
            status_code=400,
            detail="Excel файлы .xlsx форматында болушу керек"
        )

    content = file.file.read()

    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail="Файл 5 MB ашпашы керек"
        )

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

    try:
        headers = [
            str(cell.value).strip().lower()
            if cell.value is not None else ""
            for cell in sheet[1]
        ]

        if headers[:3] != ["инн", "толук аты-жөнү", "телефон"]:
            raise HTTPException(
                status_code=400,
                detail="Мамычалар: ИНН, Толук аты-жөнү, Телефон болушу керек"
            )

        school_class = db.query(Classes).filter(
            Classes.id == class_id,
            Classes.school_id == current_user.school_id
        ).first()

        if not school_class:
            raise HTTPException(
                status_code=404,
                detail="Класс табылган жок"
            )

        added_students = []
        errors = []
        seen_inns = set()

        for row_number, row in enumerate(
            sheet.iter_rows(
                min_row=2,
                max_col=3,
                values_only=True
            ),
            start=2
        ):

            inn_value, full_name, phone = row

            if all(value is None for value in row):
                continue

            inn = (
                str(inn_value).strip()
                if inn_value is not None else ""
            )

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

            if not full_name or len(str(full_name).strip()) < 3:
                errors.append({
                    "row": row_number,
                    "error": "Окуучунун аты-жөнү туура эмес"
                })
                continue

            existing = db.query(Users).filter(
                Users.inn == inn
            ).first()

            if existing:
                errors.append({
                    "row": row_number,
                    "error": "Бул ИНН мурда катталган"
                })
                continue

            password = generate_password()

            student = Users(
                inn=inn,
                full_name=str(full_name).strip(),
                role="STUDENT",
                hashed_password=hash_password(password),
                temp_password_encrypted=encrypt_temp_password(password),
                is_temp_password=True,
                phone=str(phone).strip() if phone else None,
                school_id=current_user.school_id,
                is_active=True
            )

            db.add(student)
            db.flush()

            enrollment = StudentEnrollments(
                student_id=student.id,
                class_id=class_id,
                academic_year=school_class.academic_year,
                status="ACTIVE"
            )

            db.add(enrollment)

            added_students.append({
                "inn": inn,
                "full_name": student.full_name,
                "temporary_password": password
            })

        db.commit()

        return {
            "message": "Окуучуларды жүктөө аяктады",
            "class_id": class_id,
            "total_added": len(added_students),
            "total_errors": len(errors),
            "added_students": added_students,
            "errors": errors
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Окуучуларды каттоодо ката кетти"
        )

    finally:
        workbook.close()

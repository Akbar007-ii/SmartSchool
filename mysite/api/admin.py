"""ТЗ 8-бөлүмүндөгү администратордук эндпоинттер жана убактылуу сыр сөздөр.

    POST /admin/excel/import-students        — класс боюнча окуучуларды Excel менен жүктөө
    POST /admin/excel/import-teachers        — мугалимдерди Excel менен жүктөө
    POST /admin/teacher-assignments          — мугалимди класска жана сабакка байлоо
    GET  /admin/teachers/temp-passwords      — мугалимдердин убактылуу сыр сөздөрү
    POST /admin/users/{id}/reset-password    — сыр сөздү баштапкы абалга келтирүү
    GET  /classes/{id}/temp-passwords        — класс жетекчи: өз классынын логин/сыр сөздөрү
    POST /classes/{id}/students/{sid}/reset-password — класс жетекчи: окуучунун сыр сөзүн жаңыртуу
"""
from io import BytesIO

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy.orm import Session

from mysite.api.student_import import import_students_excel
from mysite.api.teacher_import import import_teachers_excel
from mysite.db.database import get_db
from mysite.db.models import (
    Classes,
    StudentEnrollments,
    Subjects,
    TeacherAssignments,
    Users,
)
from mysite.db.schema import (
    AdminTeacherAssignmentCreate,
    SchoolAdminCreate,
    SchoolAdminUpdate,
    TeacherAssignmentOut,
)
from mysite.security.permissions import require_roles
from mysite.services.accounts import admin_row, create_school_admin, ensure_admin_limit, change_email, new_parent_code
from mysite.services.passwords import decrypt_temp_password, set_temp_password
from mysite.services.school import (
    ADMIN_ROLES,
    STAFF_ROLES,
    TEACHER_ROLES,
    class_name,
    get_class_or_404,
    is_class_teacher_of,
)

router = APIRouter(prefix="/admin", tags=["Admin"])
classes_router = APIRouter(prefix="/classes", tags=["Classes"])

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# =====================================================
# Excel массалык жүктөө (ТЗдагы даректер)
# =====================================================

@router.post("/excel/import-students")
def admin_import_students(
    class_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: Users = Depends(require_roles(*ADMIN_ROLES)),
):
    return import_students_excel(class_id=class_id, file=file, db=db, current_user=current_user)


@router.post("/excel/import-teachers")
def admin_import_teachers(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: Users = Depends(require_roles(*ADMIN_ROLES)),
):
    return import_teachers_excel(file=file, db=db, current_user=current_user)


# =====================================================
# Мугалимди класска жана сабакка байлоо
# =====================================================

@router.post("/teacher-assignments", response_model=TeacherAssignmentOut, status_code=201)
def admin_create_assignment(
    data: AdminTeacherAssignmentCreate,
    db: Session = Depends(get_db),
    current_user: Users = Depends(require_roles(*ADMIN_ROLES)),
):
    school_id = current_user.school_id

    teacher = db.query(Users).filter(
        Users.id == data.teacher_id,
        Users.school_id == school_id,
        Users.role.in_(TEACHER_ROLES),
        Users.is_active.is_(True),
    ).first()
    if teacher is None:
        raise HTTPException(status_code=404, detail="Мугалим табылган жок")

    school_class = get_class_or_404(db, data.class_id, school_id)

    subject = db.query(Subjects).filter(
        Subjects.id == data.subject_id, Subjects.school_id == school_id
    ).first()
    if subject is None:
        raise HTTPException(status_code=404, detail="Предмет табылган жок")

    academic_year = data.academic_year or school_class.academic_year

    # Бир класста бир предметти бир эле мугалим окутат
    taken = db.query(TeacherAssignments).filter(
        TeacherAssignments.class_id == school_class.id,
        TeacherAssignments.subject_id == subject.id,
        TeacherAssignments.academic_year == academic_year,
    ).first()
    if taken is not None:
        raise HTTPException(
            status_code=400,
            detail=(
                "Бул мугалим буга чейин бекитилген"
                if taken.teacher_id == teacher.id
                else "Бул класстын бул предметине башка мугалим бекитилген"
            ),
        )

    assignment = TeacherAssignments(
        teacher_id=teacher.id,
        class_id=school_class.id,
        subject_id=subject.id,
        school_id=school_id,
        academic_year=academic_year,
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment


# =====================================================
# Сыр сөздөрдү башкаруу
# =====================================================

def _password_row(user: Users) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "parent_code": user.parent_code,
        "is_temp_password": user.is_temp_password,
        # Колдонуучу сыр сөзүн алмаштыргандан кийин убактылуу сыр сөз көрүнбөйт
        "temporary_password": (
            decrypt_temp_password(user.temp_password_encrypted)
            if user.is_temp_password else None
        ),
    }


def _passwords_xlsx(title: str, rows: list[dict], filename: str) -> StreamingResponse:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = title[:31]
    sheet.append(["№", "Аты-жөнү", "Логин (почта)", "Убактылуу сыр сөз", "Ата-эне үчүн код"])
    for number, row in enumerate(rows, start=1):
        sheet.append([
            number,
            row["full_name"],
            row["email"],
            row["temporary_password"] or "өзгөртүлгөн",
            row.get("parent_code") or "",
        ])
    for column, width in zip("ABCDE", (5, 40, 32, 22, 18)):
        sheet.column_dimensions[column].width = width

    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return StreamingResponse(
        output,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/teachers/temp-passwords")
def teachers_temp_passwords(
    format: str = "json",
    db: Session = Depends(get_db),
    current_user: Users = Depends(require_roles(*ADMIN_ROLES)),
):
    teachers = db.query(Users).filter(
        Users.school_id == current_user.school_id,
        Users.role.in_(TEACHER_ROLES),
        Users.is_active.is_(True),
    ).order_by(Users.full_name).all()

    rows = [_password_row(t) for t in teachers]
    if format == "xlsx":
        return _passwords_xlsx("Мугалимдер", rows, "teachers_passwords.xlsx")
    return {"total": len(rows), "teachers": rows}


@router.post("/users/{user_id}/reset-password")
def admin_reset_password(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: Users = Depends(require_roles(*ADMIN_ROLES)),
):
    user = db.query(Users).filter(
        Users.id == user_id, Users.school_id == current_user.school_id
    ).first()
    if user is None:
        raise HTTPException(status_code=404, detail="Колдонуучу табылган жок")

    # Директор завучтун сыр сөзүн жаңырта алат; директордун сыр сөзүн —
    # платформанын администратору гана (POST /system/users/{id}/reset-password)
    deputy_by_director = user.role == "DEPUTY" and current_user.role == "DIRECTOR"
    if user.role not in TEACHER_ROLES + ("STUDENT", "PARENT") and not deputy_by_director:
        raise HTTPException(
            status_code=400,
            detail="Администратордун сыр сөзүн бул жерден өзгөртүүгө болбойт",
        )

    password = set_temp_password(user)
    db.commit()
    return {
        "message": "Сыр сөз баштапкы абалга келтирилди",
        "user_id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "temporary_password": password,
    }


# =====================================================
# Завучтар — директор кошот
# =====================================================

@router.get("/deputies")
def list_deputies(
    db: Session = Depends(get_db),
    current_user: Users = Depends(require_roles(*ADMIN_ROLES)),
):
    deputies = db.query(Users).filter(
        Users.school_id == current_user.school_id,
        Users.role == "DEPUTY",
    ).order_by(Users.full_name).all()

    rows = [admin_row(d) for d in deputies]
    # Убактылуу сыр сөздөрдү директор гана көрөт
    if current_user.role != "DIRECTOR":
        for row in rows:
            row["temporary_password"] = None
    return rows


@router.post("/deputies", status_code=201)
def create_deputy(
    data: SchoolAdminCreate,
    db: Session = Depends(get_db),
    current_user: Users = Depends(require_roles("DIRECTOR")),
):
    user, password = create_school_admin(
        db,
        school_id=current_user.school_id,
        email=data.email,
        full_name=data.full_name,
        role="DEPUTY",
    )
    db.commit()
    db.refresh(user)
    return {**admin_row(user), "temporary_password": password}


def _own_deputy_or_404(db: Session, current_user: Users, user_id: int) -> Users:
    """Директор өз мектебинин завучун гана көрөт жана өзгөртөт."""
    deputy = db.query(Users).filter(
        Users.id == user_id,
        Users.school_id == current_user.school_id,
        Users.role == "DEPUTY",
    ).first()
    if deputy is None:
        raise HTTPException(status_code=404, detail="Завуч табылган жок")
    return deputy


@router.put("/deputies/{user_id}")
def update_deputy(
    user_id: int,
    data: SchoolAdminUpdate,
    db: Session = Depends(get_db),
    current_user: Users = Depends(require_roles("DIRECTOR")),
):
    deputy = _own_deputy_or_404(db, current_user, user_id)
    update = data.model_dump(exclude_unset=True)
    if not update:
        raise HTTPException(status_code=400, detail="Өзгөртүү үчүн маалымат берилген жок")

    if "full_name" in update:
        if not update["full_name"] or not update["full_name"].strip():
            raise HTTPException(status_code=400, detail="Аты-жөнү бош болбошу керек")
        deputy.full_name = update["full_name"].strip()
    if update.get("email"):
        change_email(db, deputy, update["email"])

    db.commit()
    db.refresh(deputy)
    return admin_row(deputy)


@router.post("/deputies/{user_id}/activate")
def activate_deputy(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: Users = Depends(require_roles("DIRECTOR")),
):
    deputy = _own_deputy_or_404(db, current_user, user_id)
    if not deputy.is_active:
        # Кайра күйгүзүү да 5 завуч чегинен ашпашы керек
        ensure_admin_limit(db, deputy.school_id, "DEPUTY")
    deputy.is_active = True
    db.commit()
    return {"message": "Завуч кайра активдештирилди", "user_id": deputy.id}


@router.delete("/deputies/{user_id}")
def deactivate_deputy(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: Users = Depends(require_roles("DIRECTOR")),
):
    deputy = _own_deputy_or_404(db, current_user, user_id)

    deputy.is_active = False
    db.commit()
    return {"message": "Завуч активсиз кылынды", "user_id": deputy.id}


# =====================================================
# Класс жетекчи: өз классынын логин жана сыр сөздөрү
# =====================================================

def _ensure_class_access(user: Users, school_class: Classes) -> None:
    if user.role in ADMIN_ROLES:
        return
    if not is_class_teacher_of(user, school_class):
        raise HTTPException(
            status_code=403,
            detail="Өз классыңыздын сыр сөздөрүн гана көрө аласыз",
        )


def _class_students(db: Session, school_class: Classes) -> list[Users]:
    return (
        db.query(Users)
        .join(StudentEnrollments, StudentEnrollments.student_id == Users.id)
        .filter(
            StudentEnrollments.class_id == school_class.id,
            StudentEnrollments.status == "ACTIVE",
            Users.role == "STUDENT",
            Users.is_active.is_(True),
        )
        .order_by(Users.full_name)
        .all()
    )


@classes_router.get("/{class_id}/temp-passwords")
def class_temp_passwords(
    class_id: int,
    format: str = "json",
    db: Session = Depends(get_db),
    current_user: Users = Depends(require_roles(*STAFF_ROLES)),
):
    school_class = get_class_or_404(db, class_id, current_user.school_id)
    _ensure_class_access(current_user, school_class)

    students = _class_students(db, school_class)
    # Ата-эне коду класс жетекчи тизмени биринчи ачканда түзүлөт
    missing_codes = [student for student in students if not student.parent_code]
    for student in missing_codes:
        student.parent_code = new_parent_code(db)
        db.flush()
    if missing_codes:
        db.commit()

    rows = [_password_row(s) for s in students]
    if format == "xlsx":
        return _passwords_xlsx(
            class_name(school_class), rows, f"class_{class_id}_passwords.xlsx"
        )
    return {
        "class_id": school_class.id,
        "class_name": class_name(school_class),
        "total": len(rows),
        "students": rows,
    }


@classes_router.post("/{class_id}/students/{student_id}/reset-password")
def class_reset_student_password(
    class_id: int,
    student_id: int,
    db: Session = Depends(get_db),
    current_user: Users = Depends(require_roles(*STAFF_ROLES)),
):
    school_class = get_class_or_404(db, class_id, current_user.school_id)
    _ensure_class_access(current_user, school_class)

    student = next(
        (s for s in _class_students(db, school_class) if s.id == student_id), None
    )
    if student is None:
        raise HTTPException(status_code=404, detail="Окуучу бул класста табылган жок")

    password = set_temp_password(student)
    db.commit()
    return {
        "message": "Окуучунун сыр сөзү жаңыртылды",
        "student_id": student.id,
        "email": student.email,
        "full_name": student.full_name,
        "temporary_password": password,
    }


# Ата-эне кодун жаңылоо: эски код иштебей калат (мисалы, код бөтөн колго тийсе)
@classes_router.post("/{class_id}/students/{student_id}/parent-code")
def class_regenerate_parent_code(
    class_id: int,
    student_id: int,
    db: Session = Depends(get_db),
    current_user: Users = Depends(require_roles(*STAFF_ROLES)),
):
    school_class = get_class_or_404(db, class_id, current_user.school_id)
    _ensure_class_access(current_user, school_class)

    student = next(
        (s for s in _class_students(db, school_class) if s.id == student_id), None
    )
    if student is None:
        raise HTTPException(status_code=404, detail="Окуучу бул класста табылган жок")

    student.parent_code = new_parent_code(db)
    db.commit()
    return {"student_id": student.id, "parent_code": student.parent_code}

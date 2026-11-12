import secrets
import string

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from mysite.db.schema import StudentUpdate

from mysite.db.database import get_db
from mysite.db.models import (
    Users,
    Classes,
    StudentEnrollments
)
from mysite.db.schema import StudentCreate
from mysite.security.permissions import (
    get_current_user,
    require_roles
)
from mysite.security.hashing import hash_password
from mysite.services.passwords import encrypt_temp_password, set_temp_password

router = APIRouter(
    prefix="/students",
    tags=["Students"]
)


# 1. Мектептеги бардык окуучулар
@router.get("/")
def get_students(
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    students = db.query(Users).filter(
        Users.school_id == current_user.school_id,
        Users.role == "STUDENT"
    ).order_by(Users.full_name).all()

    result = []

    for student in students:
        enrollment = db.query(StudentEnrollments).filter(
            StudentEnrollments.student_id == student.id,
            StudentEnrollments.status == "ACTIVE"
        ).first()

        result.append({
            "id": student.id,
            "inn": student.inn,
            "full_name": student.full_name,
            "phone": student.phone,
            "class_id": enrollment.class_id if enrollment else None,
            "is_active": student.is_active
        })

    return result


# 2. Белгилүү класстын окуучулары
@router.get("/class/{class_id}")
def get_class_students(
    class_id: int,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    school_class = db.query(Classes).filter(
        Classes.id == class_id,
        Classes.school_id == current_user.school_id
    ).first()

    if not school_class:
        raise HTTPException(
            status_code=404,
            detail="Класс табылган жок"
        )

    enrollments = db.query(StudentEnrollments).filter(
        StudentEnrollments.class_id == class_id,
        StudentEnrollments.academic_year == school_class.academic_year,
        StudentEnrollments.status == "ACTIVE"
    ).all()

    result = []

    for enrollment in enrollments:
        student = db.query(Users).filter(
            Users.id == enrollment.student_id,
            Users.school_id == current_user.school_id,
            Users.role == "STUDENT"
        ).first()

        if student and student.is_active:
            result.append({
                "id": student.id,
                "inn": student.inn,
                "full_name": student.full_name,
                "phone": student.phone,
                "class_id": class_id,
                "academic_year": enrollment.academic_year
            })

    return result


# 3. Бир окуучунун маалыматы
@router.get("/{student_id}")
def get_student(
    student_id: int,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    student = db.query(Users).filter(
        Users.id == student_id,
        Users.school_id == current_user.school_id,
        Users.role == "STUDENT"
    ).first()

    if not student:
        raise HTTPException(
            status_code=404,
            detail="Окуучу табылган жок"
        )

    enrollments = db.query(StudentEnrollments).filter(
        StudentEnrollments.student_id == student.id
    ).order_by(StudentEnrollments.academic_year).all()

    return {
        "id": student.id,
        "inn": student.inn,
        "full_name": student.full_name,
        "phone": student.phone,
        "is_active": student.is_active,
        "enrollments": [
            {
                "class_id": item.class_id,
                "academic_year": item.academic_year,
                "status": item.status
            }
            for item in enrollments
        ]
    }


# 4. Окуучуну активсиз кылуу
@router.delete("/{student_id}")
def deactivate_student(
    student_id: int,
    current_user: Users = Depends(
        require_roles("DIRECTOR", "DEPUTY")
    ),
    db: Session = Depends(get_db)
):
    student = db.query(Users).filter(
        Users.id == student_id,
        Users.school_id == current_user.school_id,
        Users.role == "STUDENT"
    ).first()

    if not student:
        raise HTTPException(
            status_code=404,
            detail="Окуучу табылган жок"
        )

    student.is_active = False

    db.commit()

    return {
        "message": "Окуучу активсиз кылынды",
        "student_id": student.id
    }


# 5. Бир окуучуну каттоо
@router.post("/")
def create_student(
    data: StudentCreate,
    current_user: Users = Depends(
        require_roles("DIRECTOR", "DEPUTY")
    ),
    db: Session = Depends(get_db)
):
    # ИНН текшерүү
    if not data.inn.isdigit():
        raise HTTPException(
            status_code=400,
            detail="ИНН сандардан турушу керек"
        )

    if len(data.inn) != 14:
        raise HTTPException(
            status_code=400,
            detail="ИНН 14 цифра болушу керек"
        )

    # ИНН мурда катталганбы?
    existing = db.query(Users).filter(
        Users.inn == data.inn
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail="Бул ИНН мурда катталган"
        )

    # Классты текшерүү
    school_class = db.query(Classes).filter(
        Classes.id == data.class_id,
        Classes.school_id == current_user.school_id
    ).first()

    if not school_class:
        raise HTTPException(
            status_code=404,
            detail="Класс табылган жок"
        )

    # Убактылуу сыр сөз
    alphabet = string.ascii_letters + string.digits
    password = ''.join(
        secrets.choice(alphabet)
        for _ in range(10)
    )

    try:
        student = Users(
            inn=data.inn,
            full_name=data.full_name.strip(),
            phone=data.phone,
            role="STUDENT",
            hashed_password=hash_password(password),
            temp_password_encrypted=encrypt_temp_password(password),
            is_temp_password=True,
            school_id=current_user.school_id,
            is_active=True
        )

        db.add(student)
        db.flush()

        enrollment = StudentEnrollments(
            student_id=student.id,
            class_id=school_class.id,
            academic_year=school_class.academic_year,
            status="ACTIVE"
        )

        db.add(enrollment)
        db.commit()
        db.refresh(student)

        return {
            "message": "Окуучу ийгиликтүү катталды",
            "id": student.id,
            "inn": student.inn,
            "full_name": student.full_name,
            "role": student.role,
            "class_id": school_class.id,
            "academic_year": school_class.academic_year,
            "temporary_password": password
        }

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Окуучуну каттоодо ката кетти"
        )


# 6. Окуучунун маалыматтарын өзгөртүү
@router.put("/{student_id}")
def update_student(
    student_id: int,
    data: StudentUpdate,
    current_user: Users = Depends(
        require_roles("DIRECTOR", "DEPUTY")
    ),
    db: Session = Depends(get_db)
):
    student = db.query(Users).filter(
        Users.id == student_id,
        Users.school_id == current_user.school_id,
        Users.role == "STUDENT"
    ).first()

    if not student:
        raise HTTPException(
            status_code=404,
            detail="Окуучу табылган жок"
        )

    update_data = data.model_dump(exclude_unset=True)

    if not update_data:
        raise HTTPException(
            status_code=400,
            detail="Өзгөртүү үчүн маалымат берилген жок"
        )

    if "full_name" in update_data:
        if update_data["full_name"] is None:
            raise HTTPException(
                status_code=400,
                detail="Аты-жөнү бош болбошу керек"
            )

        student.full_name = update_data["full_name"].strip()

    if "phone" in update_data:
        student.phone = update_data["phone"]

    try:
        db.commit()
        db.refresh(student)

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Маалыматты өзгөртүүдө ката кетти"
        )

    return {
        "message": "Окуучунун маалыматы жаңыртылды",
        "id": student.id,
        "inn": student.inn,
        "full_name": student.full_name,
        "phone": student.phone
    }


# 7. Окуучунун толук окуу тарыхын көрүү
@router.get("/{student_id}/history")
def get_student_history(
    student_id: int,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    student = db.query(Users).filter(
        Users.id == student_id,
        Users.school_id == current_user.school_id,
        Users.role == "STUDENT"
    ).first()

    if not student:
        raise HTTPException(
            status_code=404,
            detail="Окуучу табылган жок"
        )

    enrollments = db.query(
        StudentEnrollments
    ).join(
        Classes,
        Classes.id == StudentEnrollments.class_id
    ).filter(
        StudentEnrollments.student_id == student.id,
        Classes.school_id == current_user.school_id
    ).order_by(
        StudentEnrollments.academic_year
    ).all()

    history = []

    for enrollment in enrollments:
        school_class = db.query(Classes).filter(
            Classes.id == enrollment.class_id
        ).first()

        history.append({
            "academic_year": enrollment.academic_year,
            "class_id": enrollment.class_id,
            "class_name": (
                f"{school_class.grade_number}-"
                f"{school_class.letter}"
            ),
            "status": enrollment.status
        })

    return {
        "student_id": student.id,
        "full_name": student.full_name,
        "history": history
    }



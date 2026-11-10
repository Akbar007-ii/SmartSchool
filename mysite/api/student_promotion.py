
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mysite.db.database import get_db
from mysite.db.models import (
    Users,
    Classes,
    StudentEnrollments
)
from mysite.db.schema import StudentPromotionRequest
from mysite.security.permissions import require_roles


router = APIRouter(
    prefix="/students/promotion",
    tags=["Student Promotion"]
)


def validate_years(source_year, target_year):
    pattern = r"^(\d{4})-(\d{4})$"

    source = re.match(pattern, source_year)
    target = re.match(pattern, target_year)

    if not source or not target:
        raise HTTPException(
            status_code=400,
            detail="Окуу жылы YYYY-YYYY форматында болушу керек"
        )

    if int(source.group(2)) != int(source.group(1)) + 1:
        raise HTTPException(
            status_code=400,
            detail="Баштапкы окуу жылы туура эмес"
        )

    if int(target.group(1)) != int(source.group(1)) + 1:
        raise HTTPException(
            status_code=400,
            detail="Кийинки окуу жылы туура эмес"
        )

    if int(target.group(2)) != int(target.group(1)) + 1:
        raise HTTPException(
            status_code=400,
            detail="Кийинки окуу жылы туура эмес"
        )


def get_source_students(db, school_id, academic_year):
    return db.query(
        StudentEnrollments,
        Users,
        Classes
    ).join(
        Users,
        Users.id == StudentEnrollments.student_id
    ).join(
        Classes,
        Classes.id == StudentEnrollments.class_id
    ).filter(
        Classes.school_id == school_id,
        StudentEnrollments.academic_year == academic_year,
        StudentEnrollments.status == "ACTIVE",
        Users.school_id == school_id,
        Users.role == "STUDENT",
        Users.is_active == True
    ).order_by(
        Classes.grade_number,
        Classes.letter,
        Users.full_name
    ).all()


# 1. Өткөрүлө турган окуучуларды алдын ала көрүү
@router.get("/preview")
def promotion_preview(
    source_academic_year: str,
    target_academic_year: str,
    current_user: Users = Depends(
        require_roles("DIRECTOR")
    ),
    db: Session = Depends(get_db)
):
    validate_years(
        source_academic_year,
        target_academic_year
    )

    records = get_source_students(
        db,
        current_user.school_id,
        source_academic_year
    )

    if not records:
        raise HTTPException(
            status_code=404,
            detail="Бул окуу жылында активдүү окуучулар табылган жок"
        )

    students = []

    for enrollment, student, school_class in records:
        next_grade = school_class.grade_number + 1

        students.append({
            "student_id": student.id,
            "full_name": student.full_name,
            "current_class": (
                f"{school_class.grade_number}-"
                f"{school_class.letter}"
            ),
            "next_class": (
                f"{next_grade}-{school_class.letter}"
                if next_grade <= 11 else None
            ),
            "will_graduate": next_grade > 11
        })

    return {
        "source_academic_year": source_academic_year,
        "target_academic_year": target_academic_year,
        "total_students": len(students),
        "students": students
    }


# 2. Окуучуларды кийинки окуу жылына өткөрүү
@router.post("/execute")
def execute_promotion(
    data: StudentPromotionRequest,
    current_user: Users = Depends(
        require_roles("DIRECTOR")
    ),
    db: Session = Depends(get_db)
):
    validate_years(
        data.source_academic_year,
        data.target_academic_year
    )

    excluded_ids = data.excluded_student_ids

    if len(excluded_ids) != len(set(excluded_ids)):
        raise HTTPException(
            status_code=400,
            detail="Өткөрүлбөй турган окуучулардын ID номерлери кайталанбашы керек"
        )

    try:
        records = get_source_students(
            db,
            current_user.school_id,
            data.source_academic_year
        )

        if not records:
            raise HTTPException(
                status_code=404,
                detail="Өткөрүлө турган окуучулар табылган жок"
            )

        source_student_ids = {
            student.id for enrollment, student, school_class in records
        }

        invalid_ids = set(excluded_ids) - source_student_ids

        if invalid_ids:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Тизмеде бул окуу жылына таандык эмес окуучулар бар",
                    "invalid_student_ids": list(invalid_ids)
                }
            )

        # Мурда өткөрүү жүргүзүлгөнбү?
        existing_target = db.query(StudentEnrollments).join(
            Users,
            Users.id == StudentEnrollments.student_id
        ).filter(
            Users.school_id == current_user.school_id,
            StudentEnrollments.academic_year == data.target_academic_year
        ).first()

        if existing_target:
            raise HTTPException(
                status_code=409,
                detail="Бул окуу жылына окуучулар мурда катталган. Кайра өткөрүүгө болбойт"
            )

        promoted = 0
        repeated = 0
        graduated = 0

        target_classes = {}

        for enrollment, student, school_class in records:

            is_excluded = student.id in excluded_ids

            if is_excluded:
                target_grade = school_class.grade_number
                repeated += 1

            else:
                target_grade = school_class.grade_number + 1

                if target_grade > 11:
                    enrollment.status = "COMPLETED"
                    graduated += 1
                    continue

                promoted += 1

            class_key = (
                target_grade,
                school_class.letter
            )

            if class_key not in target_classes:

                target_class = db.query(Classes).filter(
                    Classes.school_id == current_user.school_id,
                    Classes.grade_number == target_grade,
                    Classes.letter == school_class.letter,
                    Classes.academic_year == data.target_academic_year
                ).first()

                if not target_class:
                    target_class = Classes(
                        grade_number=target_grade,
                        letter=school_class.letter,
                        school_id=current_user.school_id,
                        academic_year=data.target_academic_year,
                        class_teacher_id=None
                    )

                    db.add(target_class)
                    db.flush()

                target_classes[class_key] = target_class

            enrollment.status = "COMPLETED"

            new_enrollment = StudentEnrollments(
                student_id=student.id,
                class_id=target_classes[class_key].id,
                academic_year=data.target_academic_year,
                status="ACTIVE"
            )

            db.add(new_enrollment)

        db.commit()

        return {
            "message": "Окуучуларды кийинки окуу жылына өткөрүү аяктады",
            "source_academic_year": data.source_academic_year,
            "target_academic_year": data.target_academic_year,
            "total_processed": len(records),
            "promoted": promoted,
            "repeated": repeated,
            "graduated": graduated,
            "excluded_student_ids": excluded_ids
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Окуучуларды өткөрүүдө ката кетти"
        )

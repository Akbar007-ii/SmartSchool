"""Мектеп ичиндеги жеткиликтүүлүк (RBAC) үчүн жалпы жардамчы функциялар."""
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from mysite.db.models import (
    Classes,
    ParentStudents,
    StudentEnrollments,
    TeacherAssignments,
    Users,
)

ADMIN_ROLES = ("DIRECTOR", "DEPUTY")
TEACHER_ROLES = ("TEACHER", "CLASS_TEACHER")
STAFF_ROLES = ADMIN_ROLES + TEACHER_ROLES


def class_name(school_class: Optional[Classes]) -> Optional[str]:
    if school_class is None:
        return None
    return f"{school_class.grade_number}-{school_class.letter}"


def get_active_enrollment(
    db: Session, student_id: int
) -> tuple[Optional[StudentEnrollments], Optional[Classes]]:
    row = (
        db.query(StudentEnrollments, Classes)
        .join(Classes, Classes.id == StudentEnrollments.class_id)
        .filter(
            StudentEnrollments.student_id == student_id,
            StudentEnrollments.status == "ACTIVE",
        )
        .order_by(StudentEnrollments.academic_year.desc())
        .first()
    )
    if row is None:
        return None, None
    return row[0], row[1]


def get_class_or_404(db: Session, class_id: int, school_id: int) -> Classes:
    school_class = db.query(Classes).filter(
        Classes.id == class_id, Classes.school_id == school_id
    ).first()
    if school_class is None:
        raise HTTPException(status_code=404, detail="Класс табылган жок")
    return school_class


def get_student_or_404(db: Session, student_id: int, school_id: int) -> Users:
    student = db.query(Users).filter(
        Users.id == student_id,
        Users.school_id == school_id,
        Users.role == "STUDENT",
    ).first()
    if student is None:
        raise HTTPException(status_code=404, detail="Окуучу табылган жок")
    return student


def get_assignment_or_404(
    db: Session, assignment_id: int, school_id: int
) -> TeacherAssignments:
    assignment = db.query(TeacherAssignments).filter(
        TeacherAssignments.id == assignment_id,
        TeacherAssignments.school_id == school_id,
    ).first()
    if assignment is None:
        raise HTTPException(status_code=404, detail="Сабак (бекитүү) табылган жок")
    return assignment


def is_class_teacher_of(user: Users, school_class: Optional[Classes]) -> bool:
    return (
        school_class is not None
        and user.role in TEACHER_ROLES
        and school_class.class_teacher_id == user.id
    )


def teaches_class(db: Session, user: Users, class_id: int) -> bool:
    if user.role not in TEACHER_ROLES:
        return False
    return db.query(TeacherAssignments.id).filter(
        TeacherAssignments.teacher_id == user.id,
        TeacherAssignments.class_id == class_id,
    ).first() is not None


def is_parent_of(db: Session, parent: Users, student_id: int) -> bool:
    if parent.role != "PARENT":
        return False
    return db.query(ParentStudents.id).filter(
        ParentStudents.parent_id == parent.id,
        ParentStudents.student_id == student_id,
    ).first() is not None


def can_view_student(db: Session, viewer: Users, student: Users) -> bool:
    """Окуучунун баа/катышуу/үй тапшырмасын ким көрө алат."""
    if viewer.school_id != student.school_id:
        return False
    if viewer.role in ADMIN_ROLES:
        return True
    if viewer.role == "STUDENT":
        return viewer.id == student.id
    if viewer.role == "PARENT":
        return is_parent_of(db, viewer, student.id)
    if viewer.role in TEACHER_ROLES:
        _, school_class = get_active_enrollment(db, student.id)
        if school_class is None:
            return False
        return is_class_teacher_of(viewer, school_class) or teaches_class(
            db, viewer, school_class.id
        )
    return False


def ensure_can_view_student(db: Session, viewer: Users, student: Users) -> None:
    if not can_view_student(db, viewer, student):
        raise HTTPException(
            status_code=403,
            detail="Бул окуучунун маалыматтарын көрүүгө уруксат жок",
        )


def resolve_student_for_viewer(
    db: Session, viewer: Users, student_id: Optional[int]
) -> Users:
    """Окуучу өзү үчүн student_id бербей эле коё алат; ата-эне баласын тандайт."""
    if student_id is None:
        if viewer.role == "STUDENT":
            return viewer
        if viewer.role == "PARENT":
            links = db.query(ParentStudents).filter(
                ParentStudents.parent_id == viewer.id
            ).all()
            if len(links) == 1:
                student_id = links[0].student_id
            else:
                raise HTTPException(
                    status_code=400, detail="student_id параметрин көрсөтүңүз"
                )
        else:
            raise HTTPException(status_code=400, detail="student_id параметрин көрсөтүңүз")

    student = get_student_or_404(db, student_id, viewer.school_id)
    ensure_can_view_student(db, viewer, student)
    return student

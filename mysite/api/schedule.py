"""Сабактардын жадыбалы (расписание).

RBAC:
  * Түзүү, өзгөртүү, өчүрүү — Директор жана Завуч гана.
  * Көрүү — мектептин бардык колдонуучулары (класс же мугалим боюнча),
    ошондой эле ар ким өзүнүн жадыбалын: GET /schedule/me.

Текшерүүлөр:
  * Бир класста бир убакта эки сабак болбойт (номери же убактысы кесилишсе).
  * Бир мугалим бир убакта эки сабак өтпөйт.
  * Бир кабинетте бир убакта эки сабак болбойт.
"""
from datetime import date, time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mysite.db.database import get_db
from mysite.db.models import Classes, ScheduleLessons, TeacherAssignments, Users
from mysite.db.schema import ScheduleLessonCreate, ScheduleLessonUpdate
from mysite.security.permissions import get_current_user, require_roles
from mysite.services.school import (
    ADMIN_ROLES,
    TEACHER_ROLES,
    class_name,
    get_active_enrollment,
    get_assignment_or_404,
    get_class_or_404,
    resolve_student_for_viewer,
)
from mysite.services.timeutils import today_local

router = APIRouter(prefix="/schedule", tags=["Schedule"])

WEEKDAYS = {
    1: "Дүйшөмбү",
    2: "Шейшемби",
    3: "Шаршемби",
    4: "Бейшемби",
    5: "Жума",
    6: "Ишемби",
}

# Коңгуроолордун демейки жадыбалы (45 мүнөттүк сабак, 4-сабактын алдында чоң тыныгуу)
DEFAULT_BELLS = {
    1: (time(8, 0), time(8, 45)),
    2: (time(8, 55), time(9, 40)),
    3: (time(9, 50), time(10, 35)),
    4: (time(10, 55), time(11, 40)),
    5: (time(11, 50), time(12, 35)),
    6: (time(12, 45), time(13, 30)),
    7: (time(13, 40), time(14, 25)),
    8: (time(14, 35), time(15, 20)),
    9: (time(15, 30), time(16, 15)),
    10: (time(16, 25), time(17, 10)),
}


def fmt(t: time) -> str:
    return t.strftime("%H:%M")


def serialize(lesson: ScheduleLessons) -> dict:
    a = lesson.assignment
    return {
        "id": lesson.id,
        "class_id": lesson.class_id,
        "class_name": class_name(lesson.school_class),
        "weekday": lesson.weekday,
        "weekday_name": WEEKDAYS[lesson.weekday],
        "lesson_number": lesson.lesson_number,
        "start_time": fmt(lesson.start_time),
        "end_time": fmt(lesson.end_time),
        "room": lesson.room,
        "assignment_id": lesson.assignment_id,
        "subject_id": a.subject_id,
        "subject_name": a.subject.name if a.subject else None,
        "teacher_id": a.teacher_id,
        "teacher_name": a.teacher.full_name if a.teacher else None,
        "academic_year": lesson.academic_year,
    }


def sort_key(lesson: ScheduleLessons):
    return (lesson.weekday, lesson.lesson_number, lesson.start_time)


def weekday_of(day: date) -> Optional[int]:
    """date -> 1..6; жекшемби болсо None."""
    value = day.isoweekday()
    return value if value <= 6 else None


def get_lesson_or_404(db: Session, lesson_id: int, school_id: int) -> ScheduleLessons:
    lesson = db.query(ScheduleLessons).filter(
        ScheduleLessons.id == lesson_id,
        ScheduleLessons.school_id == school_id,
    ).first()
    if lesson is None:
        raise HTTPException(status_code=404, detail="Сабак жадыбалдан табылган жок")
    return lesson


def check_conflicts(db: Session, lesson: ScheduleLessons, exclude_id: Optional[int] = None) -> None:
    """Класс, мугалим жана кабинет боюнча кесилишүүлөрдү текшерет (409)."""
    if lesson.start_time >= lesson.end_time:
        raise HTTPException(status_code=400, detail="Сабактын башталышы аягынан мурун болушу керек")

    same_day = db.query(ScheduleLessons).filter(
        ScheduleLessons.school_id == lesson.school_id,
        ScheduleLessons.academic_year == lesson.academic_year,
        ScheduleLessons.weekday == lesson.weekday,
    )
    if exclude_id is not None:
        same_day = same_day.filter(ScheduleLessons.id != exclude_id)

    day_name = WEEKDAYS[lesson.weekday]
    teacher_id = lesson.assignment.teacher_id

    for other in same_day.all():
        overlaps = other.start_time < lesson.end_time and lesson.start_time < other.end_time
        slot = f"{day_name}, {other.lesson_number}-сабак ({fmt(other.start_time)}–{fmt(other.end_time)})"

        if other.class_id == lesson.class_id and (
            overlaps or other.lesson_number == lesson.lesson_number
        ):
            raise HTTPException(
                status_code=409,
                detail=f"{class_name(other.school_class)} классында бул убакта сабак бар: "
                       f"{slot} — {other.assignment.subject.name}",
            )

        if not overlaps:
            continue

        if other.assignment.teacher_id == teacher_id:
            raise HTTPException(
                status_code=409,
                detail=f"Мугалим {other.assignment.teacher.full_name} бул убакта "
                       f"{class_name(other.school_class)} классында сабак өтөт: {slot}",
            )

        if lesson.room and other.room and lesson.room.strip().lower() == other.room.strip().lower():
            raise HTTPException(
                status_code=409,
                detail=f"{lesson.room} кабинети бул убакта бош эмес: "
                       f"{class_name(other.school_class)}, {slot}",
            )


def apply_times(lesson: ScheduleLessons, start: Optional[time], end: Optional[time]) -> None:
    bell_start, bell_end = DEFAULT_BELLS[lesson.lesson_number]
    lesson.start_time = start or bell_start
    lesson.end_time = end or bell_end


# =====================================================
# Коңгуроолор
# =====================================================

@router.get("/bells")
def get_bells(current_user: Users = Depends(get_current_user)):
    return {
        "weekdays": [{"weekday": k, "name": v} for k, v in WEEKDAYS.items()],
        "bells": [
            {"lesson_number": n, "start_time": fmt(s), "end_time": fmt(e)}
            for n, (s, e) in DEFAULT_BELLS.items()
        ],
    }


# =====================================================
# Көрүү
# =====================================================

@router.get("/class/{class_id}")
def class_schedule(
    class_id: int,
    weekday: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    school_class = get_class_or_404(db, class_id, current_user.school_id)

    query = db.query(ScheduleLessons).filter(
        ScheduleLessons.class_id == school_class.id,
        ScheduleLessons.academic_year == school_class.academic_year,
    )
    if weekday:
        query = query.filter(ScheduleLessons.weekday == weekday)

    return {
        "class_id": school_class.id,
        "class_name": class_name(school_class),
        "academic_year": school_class.academic_year,
        "lessons": [serialize(x) for x in sorted(query.all(), key=sort_key)],
    }


@router.get("/teacher/{teacher_id}")
def teacher_schedule(
    teacher_id: int,
    weekday: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    teacher = db.query(Users).filter(
        Users.id == teacher_id,
        Users.school_id == current_user.school_id,
        Users.role.in_(TEACHER_ROLES),
    ).first()
    if teacher is None:
        raise HTTPException(status_code=404, detail="Мугалим табылган жок")

    query = (
        db.query(ScheduleLessons)
        .join(TeacherAssignments, TeacherAssignments.id == ScheduleLessons.assignment_id)
        .filter(
            TeacherAssignments.teacher_id == teacher.id,
            ScheduleLessons.school_id == current_user.school_id,
        )
    )
    if weekday:
        query = query.filter(ScheduleLessons.weekday == weekday)

    return {
        "teacher_id": teacher.id,
        "teacher_name": teacher.full_name,
        "lessons": [serialize(x) for x in sorted(query.all(), key=sort_key)],
    }


@router.get("/me")
def my_schedule(
    day: Optional[date] = None,
    student_id: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Өз жадыбалы. `day` берилсе — ошол күндүн сабактары («Бүгүнкү жадыбал»)."""
    weekday = None
    if day is not None:
        weekday = weekday_of(day)
        if weekday is None:
            return {"date": day, "weekday": None, "weekday_name": "Жекшемби", "lessons": []}

    query = db.query(ScheduleLessons).filter(
        ScheduleLessons.school_id == current_user.school_id
    )

    if current_user.role in ("STUDENT", "PARENT"):
        student = resolve_student_for_viewer(db, current_user, student_id)
        _, school_class = get_active_enrollment(db, student.id)
        if school_class is None:
            return {"date": day, "weekday": weekday, "lessons": []}
        query = query.filter(
            ScheduleLessons.class_id == school_class.id,
            ScheduleLessons.academic_year == school_class.academic_year,
        )
    elif current_user.role in TEACHER_ROLES:
        query = query.join(
            TeacherAssignments, TeacherAssignments.id == ScheduleLessons.assignment_id
        ).filter(TeacherAssignments.teacher_id == current_user.id)
    else:
        raise HTTPException(
            status_code=400,
            detail="Директор/завуч класс же мугалим боюнча көрөт: /schedule/class/{id}, /schedule/teacher/{id}",
        )

    if weekday:
        query = query.filter(ScheduleLessons.weekday == weekday)

    return {
        "date": day,
        "weekday": weekday,
        "weekday_name": WEEKDAYS.get(weekday) if weekday else None,
        "lessons": [serialize(x) for x in sorted(query.all(), key=sort_key)],
    }


@router.get("/today")
def today_schedule(
    student_id: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return my_schedule(day=today_local(), student_id=student_id, current_user=current_user, db=db)


# =====================================================
# Түзүү / өзгөртүү / өчүрүү — Директор жана Завуч
# =====================================================

@router.post("", status_code=201)
def create_lesson(
    data: ScheduleLessonCreate,
    current_user: Users = Depends(require_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    assignment = get_assignment_or_404(db, data.assignment_id, current_user.school_id)

    lesson = ScheduleLessons(
        school_id=current_user.school_id,
        class_id=assignment.class_id,
        assignment_id=assignment.id,
        academic_year=assignment.academic_year,
        weekday=data.weekday,
        lesson_number=data.lesson_number,
        room=data.room.strip() if data.room else None,
    )
    lesson.assignment = assignment
    lesson.school_class = assignment.school_class
    apply_times(lesson, data.start_time, data.end_time)

    check_conflicts(db, lesson)

    db.add(lesson)
    db.commit()
    db.refresh(lesson)
    return serialize(lesson)


@router.put("/{lesson_id}")
def update_lesson(
    lesson_id: int,
    data: ScheduleLessonUpdate,
    current_user: Users = Depends(require_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    lesson = get_lesson_or_404(db, lesson_id, current_user.school_id)
    update = data.model_dump(exclude_unset=True)
    if not update:
        raise HTTPException(status_code=400, detail="Өзгөртүү үчүн маалымат берилген жок")

    if update.get("assignment_id") is not None:
        assignment = get_assignment_or_404(db, update["assignment_id"], current_user.school_id)
        if assignment.class_id != lesson.class_id:
            raise HTTPException(
                status_code=400,
                detail="Бекитүү бул класска таандык эмес. Башка класска сабак кошуу үчүн жаңы сабак түзүңүз",
            )
        lesson.assignment_id = assignment.id
        lesson.assignment = assignment

    number_changed = "lesson_number" in update and update["lesson_number"] != lesson.lesson_number
    if update.get("weekday") is not None:
        lesson.weekday = update["weekday"]
    if update.get("lesson_number") is not None:
        lesson.lesson_number = update["lesson_number"]
    if "room" in update:
        lesson.room = update["room"].strip() if update["room"] else None

    # Сабактын номери өзгөрсө жана убакыт берилбесе — коңгуроо жадыбалы боюнча
    if number_changed or "start_time" in update or "end_time" in update:
        bell_start, bell_end = DEFAULT_BELLS[lesson.lesson_number]
        lesson.start_time = update.get("start_time") or (bell_start if number_changed else lesson.start_time)
        lesson.end_time = update.get("end_time") or (bell_end if number_changed else lesson.end_time)

    # Текшерүү учурунда өзгөртүүлөр базага эрте жазылбашы үчүн; кесилишүү
    # табылса, сессиядагы сакталбаган өзгөртүүлөр жокко чыгарылат
    try:
        with db.no_autoflush:
            check_conflicts(db, lesson, exclude_id=lesson.id)
    except HTTPException:
        db.rollback()
        raise

    db.commit()
    db.refresh(lesson)
    return serialize(lesson)


@router.delete("/{lesson_id}")
def delete_lesson(
    lesson_id: int,
    current_user: Users = Depends(require_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    lesson = get_lesson_or_404(db, lesson_id, current_user.school_id)
    db.delete(lesson)
    db.commit()
    return {"message": "Сабак жадыбалдан өчүрүлдү"}

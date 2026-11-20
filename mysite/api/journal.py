"""Интерактивдүү электрондук журнал жана күндөлүк.

RBAC (ТЗ 3-бөлүм):
  * Баа/катышууну сабакка бекитилген мугалим ГАНА коёт (өз сабагына).
  * Класс жетекчи өз классынын бардык сабактарын көрөт, баа коё албайт (өз сабагынан башка).
  * Директор/Завуч бардыгын көрөт (көрүү гана).
  * Окуучу/ата-эне өз күндөлүгүн көрөт.
"""
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mysite.db.database import get_db
from mysite.db.models import (
    AbsenceRequests,
    Classes,
    JournalEntries,
    PeriodGrades,
    ScheduleLessons,
    StudentEnrollments,
    Subjects,
    TeacherAssignments,
    Users,
)
from mysite.db.schema import JournalSave, PeriodGradesSave
from mysite.security.permissions import get_current_user, require_roles
from mysite.services.rating import entry_xp, recompute_subject_xp, sync_badges
from mysite.services.school import (
    ADMIN_ROLES,
    STAFF_ROLES,
    TEACHER_ROLES,
    class_name,
    get_active_enrollment,
    get_assignment_or_404,
    get_class_or_404,
    is_class_teacher_of,
    resolve_student_for_viewer,
)
from mysite.services.timeutils import today_local

router = APIRouter(prefix="/journal", tags=["Journal"])


def serialize_assignment(a: TeacherAssignments) -> dict:
    return {
        "id": a.id,
        "class_id": a.class_id,
        "class_name": class_name(a.school_class),
        "subject_id": a.subject_id,
        "subject_name": a.subject.name if a.subject else None,
        "teacher_id": a.teacher_id,
        "teacher_name": a.teacher.full_name if a.teacher else None,
        "academic_year": a.academic_year,
    }


def class_students(db: Session, school_class: Classes) -> list[Users]:
    return (
        db.query(Users)
        .join(StudentEnrollments, StudentEnrollments.student_id == Users.id)
        .filter(
            StudentEnrollments.class_id == school_class.id,
            StudentEnrollments.academic_year == school_class.academic_year,
            StudentEnrollments.status == "ACTIVE",
            Users.role == "STUDENT",
            Users.is_active.is_(True),
        )
        .order_by(Users.full_name)
        .all()
    )


def excused_student_ids(db: Session, class_id: int, day: date) -> set[int]:
    return {
        r.student_id
        for r in db.query(AbsenceRequests.student_id).filter(
            AbsenceRequests.class_id == class_id,
            AbsenceRequests.target_date == day,
            AbsenceRequests.status == "APPROVED",
        )
    }


def ensure_can_view_assignment(db: Session, user: Users, assignment: TeacherAssignments):
    if user.role in ADMIN_ROLES:
        return
    if user.role in TEACHER_ROLES:
        if assignment.teacher_id == user.id:
            return
        if is_class_teacher_of(user, assignment.school_class):
            return
    raise HTTPException(status_code=403, detail="Бул журналды көрүүгө уруксат жок")


# =====================================================
# 1. Журналдар тизмеси (класс + предмет)
# =====================================================

@router.get("/assignments")
def list_journal_assignments(
    class_id: Optional[int] = None,
    current_user: Users = Depends(require_roles(*STAFF_ROLES)),
    db: Session = Depends(get_db),
):
    query = db.query(TeacherAssignments).filter(
        TeacherAssignments.school_id == current_user.school_id
    )

    if current_user.role in TEACHER_ROLES:
        led = [
            c.id for c in db.query(Classes.id).filter(
                Classes.class_teacher_id == current_user.id
            )
        ]
        query = query.filter(
            (TeacherAssignments.teacher_id == current_user.id)
            | (TeacherAssignments.class_id.in_(led or [-1]))
        )

    if class_id:
        query = query.filter(TeacherAssignments.class_id == class_id)

    assignments = query.all()
    result = [serialize_assignment(a) for a in assignments]
    for item in result:
        item["can_edit"] = item["teacher_id"] == current_user.id
    result.sort(key=lambda x: (x["class_name"] or "", x["subject_name"] or ""))
    return result


# =====================================================
# 2. Бир сабактын бир күнкү журналы
# =====================================================

@router.get("")
def get_journal(
    assignment_id: int,
    day: Optional[date] = None,
    current_user: Users = Depends(require_roles(*STAFF_ROLES)),
    db: Session = Depends(get_db),
):
    day = day or today_local()
    assignment = get_assignment_or_404(db, assignment_id, current_user.school_id)
    ensure_can_view_assignment(db, current_user, assignment)

    students = class_students(db, assignment.school_class)
    entries = {
        e.student_id: e
        for e in db.query(JournalEntries).filter(
            JournalEntries.assignment_id == assignment.id,
            JournalEntries.date == day,
        )
    }
    excused = excused_student_ids(db, assignment.class_id, day)

    rows = []
    for number, student in enumerate(students, start=1):
        entry = entries.get(student.id)
        rows.append({
            "number": number,
            "student_id": student.id,
            "full_name": student.full_name,
            "entry_id": entry.id if entry else None,
            "grade_value": entry.grade_value if entry else None,
            "attendance": entry.attendance if entry else ("С" if student.id in excused else None),
            "comment": entry.comment if entry else None,
            # Сурануу бекитилген — «Сурануу» мамычасы
            "excused": student.id in excused,
        })

    return {
        "assignment": serialize_assignment(assignment),
        "date": day,
        "can_edit": assignment.teacher_id == current_user.id,
        "students": rows,
    }


# =====================================================
# 3. Баа жана катышуу коюу (өз сабагына гана)
# =====================================================

@router.put("")
def save_journal(
    data: JournalSave,
    current_user: Users = Depends(require_roles(*TEACHER_ROLES)),
    db: Session = Depends(get_db),
):
    assignment = get_assignment_or_404(db, data.assignment_id, current_user.school_id)

    if assignment.teacher_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Сиз бул класстын бул сабагына бекитилген эмессиз",
        )

    if data.date > today_local():
        raise HTTPException(status_code=400, detail="Келечектеги күнгө баа коюуга болбойт")

    allowed_ids = {s.id for s in class_students(db, assignment.school_class)}
    excused = excused_student_ids(db, assignment.class_id, data.date)

    seen = set()
    for item in data.entries:
        if item.student_id in seen:
            raise HTTPException(status_code=400, detail="Бир окуучу эки жолу берилди")
        seen.add(item.student_id)
        if item.student_id not in allowed_ids:
            raise HTTPException(
                status_code=400,
                detail=f"Окуучу (id={item.student_id}) бул класста окубайт",
            )
        if item.student_id in excused and item.grade_value is not None:
            raise HTTPException(
                status_code=400,
                detail=f"Окуучу (id={item.student_id}) бул күнү себептүү сураган — баа коюуга болбойт",
            )
        if item.attendance == "С" and item.student_id not in excused:
            raise HTTPException(
                status_code=400,
                detail="«С» белгиси класс жетекчи суранууну бекиткенде гана автоматтык коюлат",
            )
        if item.attendance in ("Ж",) and item.grade_value is not None:
            raise HTTPException(
                status_code=400,
                detail="Сабакта жок окуучуга баа коюуга болбойт",
            )

    existing = {
        e.student_id: e
        for e in db.query(JournalEntries).filter(
            JournalEntries.assignment_id == assignment.id,
            JournalEntries.date == data.date,
            JournalEntries.student_id.in_(seen),
        )
    }

    saved, deleted = 0, 0
    for item in data.entries:
        attendance = "С" if item.student_id in excused else item.attendance
        entry = existing.get(item.student_id)

        if item.grade_value is None and attendance is None and not item.comment:
            if entry is not None:
                db.delete(entry)
                deleted += 1
            continue

        if entry is None:
            entry = JournalEntries(
                assignment_id=assignment.id,
                student_id=item.student_id,
                school_id=assignment.school_id,
                date=data.date,
                created_by=current_user.id,
            )
            db.add(entry)

        entry.grade_value = item.grade_value
        entry.attendance = attendance
        entry.comment = item.comment
        saved += 1

    db.flush()
    recompute_subject_xp(
        db, assignment.school_id, {(sid, assignment.subject_id) for sid in seen}
    )
    sync_badges(db, assignment.school_id)
    db.commit()

    return {
        "message": "Журнал сакталды",
        "saved": saved,
        "deleted": deleted,
    }


@router.delete("/entries/{entry_id}")
def delete_journal_entry(
    entry_id: int,
    current_user: Users = Depends(require_roles(*TEACHER_ROLES)),
    db: Session = Depends(get_db),
):
    entry = db.query(JournalEntries).filter(
        JournalEntries.id == entry_id,
        JournalEntries.school_id == current_user.school_id,
    ).first()
    if entry is None:
        raise HTTPException(status_code=404, detail="Жазуу табылган жок")
    if entry.assignment.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="Өз сабагыңыздын жазуусун гана өчүрө аласыз")

    pair = (entry.student_id, entry.assignment.subject_id)
    db.delete(entry)
    db.flush()
    recompute_subject_xp(db, current_user.school_id, {pair})
    sync_badges(db, current_user.school_id)
    db.commit()
    return {"message": "Жазуу өчүрүлдү"}


# =====================================================
# 4. Окуучунун күндөлүгү (окуучу / ата-эне / мугалим)
# =====================================================

def _entries_for_student(db: Session, student_id: int, date_from: date, date_to: date):
    return (
        db.query(JournalEntries, TeacherAssignments, Subjects, Users)
        .join(TeacherAssignments, TeacherAssignments.id == JournalEntries.assignment_id)
        .join(Subjects, Subjects.id == TeacherAssignments.subject_id)
        .join(Users, Users.id == TeacherAssignments.teacher_id)
        .filter(
            JournalEntries.student_id == student_id,
            JournalEntries.date >= date_from,
            JournalEntries.date <= date_to,
        )
        .order_by(JournalEntries.date.desc(), Subjects.name)
        .all()
    )


@router.get("/diary")
def get_diary(
    student_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    student = resolve_student_for_viewer(db, current_user, student_id)
    date_to = date_to or today_local()
    date_from = date_from or (date_to - timedelta(days=6))

    if (date_to - date_from).days > 366:
        raise HTTPException(status_code=400, detail="Аралык 1 жылдан ашпашы керек")

    days = defaultdict(list)
    for entry, assignment, subject, teacher in _entries_for_student(db, student.id, date_from, date_to):
        days[entry.date].append({
            "entry_id": entry.id,
            "subject_id": subject.id,
            "subject_name": subject.name,
            "teacher_name": teacher.full_name,
            "grade_value": entry.grade_value,
            "attendance": entry.attendance,
            "comment": entry.comment,
            "xp": entry_xp(entry.grade_value, entry.attendance),
        })

    return {
        "student_id": student.id,
        "full_name": student.full_name,
        "date_from": date_from,
        "date_to": date_to,
        "days": [
            {"date": d, "lessons": lessons}
            for d, lessons in sorted(days.items(), reverse=True)
        ],
    }


# =====================================================
# 5. Предметтер боюнча жыйынтык жана өсүү темпи (ата-эне үчүн)
# =====================================================

@router.get("/summary")
def get_summary(
    student_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    student = resolve_student_for_viewer(db, current_user, student_id)
    date_to = date_to or today_local()
    date_from = date_from or (date_to - timedelta(days=365))

    subjects = {}
    attendance_total = defaultdict(int)

    for entry, _, subject, _ in _entries_for_student(db, student.id, date_from, date_to):
        s = subjects.setdefault(subject.id, {
            "subject_id": subject.id,
            "subject_name": subject.name,
            "grades": [],
            "monthly": defaultdict(list),
            "attendance": defaultdict(int),
            "xp": 0,
        })
        if entry.grade_value is not None:
            s["grades"].append(entry.grade_value)
            s["monthly"][entry.date.strftime("%Y-%m")].append(entry.grade_value)
        if entry.attendance:
            s["attendance"][entry.attendance] += 1
            attendance_total[entry.attendance] += 1
        s["xp"] += entry_xp(entry.grade_value, entry.attendance)

    result = []
    for s in subjects.values():
        grades = s.pop("grades")
        monthly = s.pop("monthly")
        s["grades_count"] = len(grades)
        s["average"] = round(sum(grades) / len(grades), 2) if grades else None
        s["last_grades"] = grades[:5]
        s["attendance"] = dict(s["attendance"])
        s["trend"] = [
            {"month": m, "average": round(sum(v) / len(v), 2)}
            for m, v in sorted(monthly.items())
        ]
        result.append(s)

    # Чейректик жана жылдык жыйынтык баалар — окуучунун акыркы окуу жылы боюнча
    period_rows = (
        db.query(PeriodGrades, TeacherAssignments)
        .join(TeacherAssignments, TeacherAssignments.id == PeriodGrades.assignment_id)
        .filter(PeriodGrades.student_id == student.id)
        .all()
    )
    latest_year = max((a.academic_year for _, a in period_rows), default=None)
    period_by_subject = defaultdict(dict)
    for grade, assignment in period_rows:
        if assignment.academic_year == latest_year:
            period_by_subject[assignment.subject_id][grade.period] = grade.grade_value
    for s in result:
        s["period_grades"] = period_by_subject.get(s["subject_id"], {})

    result.sort(key=lambda x: x["subject_name"])

    all_grades = [
        e.grade_value
        for e, _, _, _ in _entries_for_student(db, student.id, date_from, date_to)
        if e.grade_value is not None
    ]

    return {
        "student_id": student.id,
        "full_name": student.full_name,
        "overall_average": round(sum(all_grades) / len(all_grades), 2) if all_grades else None,
        "attendance": dict(attendance_total),
        "subjects": result,
    }


# =====================================================
# 6. Класс жетекчи: класстын бир күнкү бардык сабактары
# =====================================================

@router.get("/class/{class_id}")
def get_class_day(
    class_id: int,
    day: Optional[date] = None,
    current_user: Users = Depends(require_roles(*STAFF_ROLES)),
    db: Session = Depends(get_db),
):
    day = day or today_local()
    school_class = get_class_or_404(db, class_id, current_user.school_id)

    if current_user.role in TEACHER_ROLES and not is_class_teacher_of(current_user, school_class):
        raise HTTPException(status_code=403, detail="Өз классыңыздын журналын гана көрө аласыз")

    students = class_students(db, school_class)
    excused = excused_student_ids(db, class_id, day)

    entries = (
        db.query(JournalEntries, TeacherAssignments)
        .join(TeacherAssignments, TeacherAssignments.id == JournalEntries.assignment_id)
        .filter(
            TeacherAssignments.class_id == class_id,
            JournalEntries.date == day,
        )
        .all()
    )
    by_student = defaultdict(list)
    for entry, assignment in entries:
        by_student[entry.student_id].append({
            "subject_id": assignment.subject_id,
            "subject_name": assignment.subject.name,
            "grade_value": entry.grade_value,
            "attendance": entry.attendance,
        })

    return {
        "class_id": class_id,
        "class_name": class_name(school_class),
        "date": day,
        "students": [
            {
                "number": i,
                "student_id": s.id,
                "full_name": s.full_name,
                "excused": s.id in excused,
                "lessons": by_student.get(s.id, []),
            }
            for i, s in enumerate(students, start=1)
        ],
    }


# =====================================================
# 7. Бир айлык табель (класс + предмет)
# =====================================================

def average_of(grades: list[int]) -> Optional[float]:
    return round(sum(grades) / len(grades), 2) if grades else None


def month_range(month: Optional[str]) -> tuple[date, date]:
    """'2026-11' → (2026-11-01, 2026-11-30). Берилбесе — учурдагы ай."""
    try:
        year_number, month_number = (int(part) for part in (month or today_local().strftime("%Y-%m")).split("-"))
        first_day = date(year_number, month_number, 1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Ай YYYY-MM форматында болушу керек")
    next_month = date(first_day.year + first_day.month // 12, first_day.month % 12 + 1, 1)
    return first_day, next_month - timedelta(days=1)


def month_cell(entry: JournalEntries) -> dict:
    return {
        "date": entry.date,
        "entry_id": entry.id,
        "grade_value": entry.grade_value,
        "attendance": entry.attendance,
        "comment": entry.comment,
    }


@router.get("/month")
def get_journal_month(
    assignment_id: int,
    month: Optional[str] = None,
    current_user: Users = Depends(require_roles(*STAFF_ROLES)),
    db: Session = Depends(get_db),
):
    """Табель: окуучулар × айдын күндөрү. Клетка — баа жана катышуу белгиси."""
    first_day, last_day = month_range(month)

    assignment = get_assignment_or_404(db, assignment_id, current_user.school_id)
    ensure_can_view_assignment(db, current_user, assignment)

    students = class_students(db, assignment.school_class)
    entries = db.query(JournalEntries).filter(
        JournalEntries.assignment_id == assignment.id,
        JournalEntries.date >= first_day,
        JournalEntries.date <= last_day,
    ).all()
    excused = {
        (r.student_id, r.target_date)
        for r in db.query(AbsenceRequests.student_id, AbsenceRequests.target_date).filter(
            AbsenceRequests.class_id == assignment.class_id,
            AbsenceRequests.target_date >= first_day,
            AbsenceRequests.target_date <= last_day,
            AbsenceRequests.status == "APPROVED",
        )
    }
    # Жадыбал боюнча бул сабак өтүүчү апта күндөрү (1 — дүйшөмбү)
    lesson_weekdays = sorted({
        weekday for (weekday,) in db.query(ScheduleLessons.weekday).filter(
            ScheduleLessons.assignment_id == assignment.id
        )
    })

    cells_by_student = defaultdict(list)
    for entry in entries:
        cells_by_student[entry.student_id].append(entry)

    rows = []
    for number, student in enumerate(students, start=1):
        student_entries = sorted(cells_by_student.get(student.id, []), key=lambda e: e.date)
        cells = [month_cell(e) for e in student_entries]
        entry_dates = {e.date for e in student_entries}
        # Сурануу бекитилген, бирок мугалим али журналга жазбаган күндөр
        for student_id, day in excused:
            if student_id == student.id and day not in entry_dates:
                cells.append({
                    "date": day, "entry_id": None, "grade_value": None,
                    "attendance": "С", "comment": None,
                })
        cells.sort(key=lambda c: c["date"])
        grades = [e.grade_value for e in student_entries if e.grade_value is not None]
        rows.append({
            "number": number,
            "student_id": student.id,
            "full_name": student.full_name,
            "cells": cells,
            "average": average_of(grades),
            "grades_count": len(grades),
            "absent_count": sum(1 for c in cells if c["attendance"] in ("Ж", "С")),
        })

    return {
        "assignment": serialize_assignment(assignment),
        "month": first_day.strftime("%Y-%m"),
        "date_from": first_day,
        "date_to": last_day,
        "can_edit": assignment.teacher_id == current_user.id,
        "lesson_weekdays": lesson_weekdays,
        "students": rows,
    }


# =====================================================
# 7б. Окуучунун айлык табели (окуучу / ата-эне)
# =====================================================

@router.get("/my-month")
def get_student_month(
    student_id: Optional[int] = None,
    month: Optional[str] = None,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Окуучунун табели: сабактар × айдын күндөрү."""
    student = resolve_student_for_viewer(db, current_user, student_id)
    first_day, last_day = month_range(month)

    # Сабак тизмеси: учурдагы класстын бардык сабактары + ушул айда баасы бар сабактар
    subjects = {}
    _, school_class = get_active_enrollment(db, student.id)
    if school_class is not None:
        for assignment in db.query(TeacherAssignments).filter(
            TeacherAssignments.class_id == school_class.id,
            TeacherAssignments.academic_year == school_class.academic_year,
        ):
            if assignment.subject is not None:
                subjects[assignment.subject_id] = assignment.subject.name

    cells_by_subject = defaultdict(list)
    for entry, _, subject, _ in _entries_for_student(db, student.id, first_day, last_day):
        subjects[subject.id] = subject.name
        cells_by_subject[subject.id].append(entry)

    rows = []
    for number, (subject_id, subject_name) in enumerate(sorted(subjects.items(), key=lambda item: item[1]), start=1):
        entries = sorted(cells_by_subject.get(subject_id, []), key=lambda e: e.date)
        grades = [e.grade_value for e in entries if e.grade_value is not None]
        rows.append({
            "number": number,
            "subject_id": subject_id,
            "subject_name": subject_name,
            "cells": [month_cell(e) for e in entries],
            "average": average_of(grades),
            "grades_count": len(grades),
            "absent_count": sum(1 for e in entries if e.attendance in ("Ж", "С")),
        })

    return {
        "student_id": student.id,
        "full_name": student.full_name,
        "month": first_day.strftime("%Y-%m"),
        "date_from": first_day,
        "date_to": last_day,
        "rows": rows,
    }


# =====================================================
# 8. Чейректик жана жылдык баалар
# =====================================================

def academic_quarters(academic_year: str) -> list[dict]:
    """Окуу жылынын чейректери.

    Чейректин чеги мектептен мектепке бир аз айырмаланат, ошондуктан ай боюнча
    тегеректелет: эс алуу күндөрүндөгү баа кийинки чейрекке кошулат.
    """
    try:
        start_year = int(academic_year.split("-")[0])
    except ValueError:
        raise HTTPException(status_code=400, detail="Окуу жылы туура эмес")
    return [
        {"key": "Q1", "start": date(start_year, 9, 1), "end": date(start_year, 10, 31)},
        {"key": "Q2", "start": date(start_year, 11, 1), "end": date(start_year, 12, 31)},
        {"key": "Q3", "start": date(start_year + 1, 1, 1), "end": date(start_year + 1, 3, 31)},
        {"key": "Q4", "start": date(start_year + 1, 4, 1), "end": date(start_year + 1, 8, 31)},
    ]


@router.get("/periods")
def get_period_grades(
    assignment_id: int,
    current_user: Users = Depends(require_roles(*STAFF_ROLES)),
    db: Session = Depends(get_db),
):
    """Ар бир окуучунун чейрек боюнча орточо баасы жана мугалим койгон жыйынтык баа."""
    assignment = get_assignment_or_404(db, assignment_id, current_user.school_id)
    ensure_can_view_assignment(db, current_user, assignment)

    quarters = academic_quarters(assignment.academic_year)
    students = class_students(db, assignment.school_class)
    entries = db.query(JournalEntries.student_id, JournalEntries.date, JournalEntries.grade_value).filter(
        JournalEntries.assignment_id == assignment.id,
        JournalEntries.date >= quarters[0]["start"],
        JournalEntries.date <= quarters[-1]["end"],
        JournalEntries.grade_value.isnot(None),
    ).all()
    finals = {
        (g.student_id, g.period): g.grade_value
        for g in db.query(PeriodGrades).filter(PeriodGrades.assignment_id == assignment.id)
    }

    grades_by_quarter = defaultdict(list)
    for student_id, day, grade_value in entries:
        for quarter in quarters:
            if quarter["start"] <= day <= quarter["end"]:
                grades_by_quarter[(student_id, quarter["key"])].append(grade_value)

    rows = []
    for number, student in enumerate(students, start=1):
        grades = {}
        for quarter in quarters:
            values = grades_by_quarter.get((student.id, quarter["key"]), [])
            grades[quarter["key"]] = {
                "average": average_of(values),
                "grades_count": len(values),
                "final": finals.get((student.id, quarter["key"])),
            }
        # Жылдык баанын сунушу — чейректик жыйынтык баалардын орточосу
        quarter_finals = [g["final"] for g in grades.values() if g["final"] is not None]
        grades["YEAR"] = {
            "average": average_of(quarter_finals),
            "grades_count": len(quarter_finals),
            "final": finals.get((student.id, "YEAR")),
        }
        rows.append({
            "number": number,
            "student_id": student.id,
            "full_name": student.full_name,
            "grades": grades,
        })

    today = today_local()
    current = next((q["key"] for q in quarters if q["start"] <= today <= q["end"]), None)

    return {
        "assignment": serialize_assignment(assignment),
        "academic_year": assignment.academic_year,
        "can_edit": assignment.teacher_id == current_user.id,
        "current_period": current,
        "periods": quarters,
        "students": rows,
    }


@router.put("/periods")
def save_period_grades(
    data: PeriodGradesSave,
    current_user: Users = Depends(require_roles(*TEACHER_ROLES)),
    db: Session = Depends(get_db),
):
    assignment = get_assignment_or_404(db, data.assignment_id, current_user.school_id)
    if assignment.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="Сиз бул класстын бул сабагына бекитилген эмессиз")

    quarters = academic_quarters(assignment.academic_year)
    starts = {q["key"]: q["start"] for q in quarters}
    # Жылдык баа 4-чейрек башталганда коюлат
    period_start = starts.get(data.period, starts["Q4"])
    if period_start > today_local():
        raise HTTPException(status_code=400, detail="Бул чейрек али башталган жок")

    allowed_ids = {s.id for s in class_students(db, assignment.school_class)}
    seen = set()
    for item in data.entries:
        if item.student_id in seen:
            raise HTTPException(status_code=400, detail="Бир окуучу эки жолу берилди")
        seen.add(item.student_id)
        if item.student_id not in allowed_ids:
            raise HTTPException(status_code=400, detail=f"Окуучу (id={item.student_id}) бул класста окубайт")

    existing = {
        g.student_id: g
        for g in db.query(PeriodGrades).filter(
            PeriodGrades.assignment_id == assignment.id,
            PeriodGrades.period == data.period,
            PeriodGrades.student_id.in_(seen),
        )
    }

    saved, deleted = 0, 0
    for item in data.entries:
        grade = existing.get(item.student_id)
        if item.grade_value is None:
            if grade is not None:
                db.delete(grade)
                deleted += 1
            continue
        if grade is None:
            grade = PeriodGrades(
                assignment_id=assignment.id,
                student_id=item.student_id,
                school_id=assignment.school_id,
                period=data.period,
            )
            db.add(grade)
        grade.grade_value = item.grade_value
        grade.updated_by = current_user.id
        saved += 1

    db.commit()
    return {"message": "Жыйынтык баалар сакталды", "saved": saved, "deleted": deleted}

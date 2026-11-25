"""Окуу программасы (календардык-тематикалык план).

Директор же завуч программаны предмет+параллель боюнча Excel'ден жүктөйт.
Мугалим өз класстарында темаларды «өтүлдү» деп белгилейт; прогресс ар бир класста өзүнчө.
"""
from datetime import date
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from openpyxl import load_workbook
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from mysite.db.database import get_db
from mysite.db.models import (
    Classes,
    CurriculumPrograms,
    CurriculumProgress,
    CurriculumTopics,
    Subjects,
    TeacherAssignments,
    Users,
)
from mysite.security.permissions import require_roles
from mysite.services.school import ADMIN_ROLES, STAFF_ROLES, class_name, get_class_or_404
from mysite.services.text_checks import validate_free_text
from mysite.services.timeutils import current_academic_year, today_local

router = APIRouter(prefix="/programs", tags=["Curriculum programs"])

MAX_FILE_SIZE = 5 * 1024 * 1024

# Excel'деги мамычалардын аталыштары (кыргызча же орусча, тартиби маанилүү эмес)
COLUMN_NAMES = {
    "section": ("бөлүм", "раздел"),
    "title": ("тема",),
    "hours": ("саат", "часы", "час"),
    "week": ("апта", "неделя"),
    "goals": ("максаттар", "максат", "цели", "цель"),
    "materials": ("материалдар", "материалы"),
}


class TopicProgressUpdate(BaseModel):
    done: bool
    note: Optional[str] = Field(default=None, max_length=500)


def current_week(today: date) -> int:
    """Окуу жылынын учурдагы аптасы: 1-сентябрдан баштап эсептелет."""
    start_year = int(current_academic_year(today)[:4])
    return (today - date(start_year, 9, 1)).days // 7 + 1


def get_program(db: Session, school_id: int, subject_id: int, grade_number: int):
    return db.query(CurriculumPrograms).filter(
        CurriculumPrograms.school_id == school_id,
        CurriculumPrograms.subject_id == subject_id,
        CurriculumPrograms.grade_number == grade_number,
    ).first()


def ensure_can_mark(db: Session, user: Users, class_id: int, subject_id: int) -> None:
    """Директор, завуч же ушул класста ушул предметти окуткан мугалим гана."""
    if user.role in ADMIN_ROLES:
        return
    assigned = db.query(TeacherAssignments.id).filter(
        TeacherAssignments.teacher_id == user.id,
        TeacherAssignments.class_id == class_id,
        TeacherAssignments.subject_id == subject_id,
    ).first()
    if not assigned:
        raise HTTPException(status_code=403, detail="Бул класстагы бул предметтин программасы сизге жеткиликсиз")


# 1. Карточкалар: мугалимге — өз класстары, директорго жана завучка — бүт мектеп
@router.get("")
def list_programs(
    current_user: Users = Depends(require_roles(*STAFF_ROLES)),
    db: Session = Depends(get_db),
):
    query = db.query(TeacherAssignments, Classes, Subjects, Users).join(
        Classes, Classes.id == TeacherAssignments.class_id
    ).join(
        Subjects, Subjects.id == TeacherAssignments.subject_id
    ).join(
        Users, Users.id == TeacherAssignments.teacher_id
    ).filter(
        TeacherAssignments.school_id == current_user.school_id,
        Classes.academic_year == current_academic_year(),
    )
    if current_user.role not in ADMIN_ROLES:
        query = query.filter(TeacherAssignments.teacher_id == current_user.id)

    programs = {
        (program.subject_id, program.grade_number): program
        for program in db.query(CurriculumPrograms).filter(
            CurriculumPrograms.school_id == current_user.school_id
        )
    }
    week = current_week(today_local())
    cards = {}

    for assignment, school_class, subject, teacher in query.order_by(
        Classes.grade_number, Classes.letter, Subjects.name
    ):
        key = (school_class.id, subject.id)
        if key in cards:
            continue

        program = programs.get((subject.id, school_class.grade_number))
        topics = program.topics if program else []
        done_ids = {
            topic_id for (topic_id,) in db.query(CurriculumProgress.topic_id).filter(
                CurriculumProgress.class_id == school_class.id,
                CurriculumProgress.topic_id.in_([topic.id for topic in topics]),
            )
        } if topics else set()
        planned = sum(1 for topic in topics if topic.week is not None and topic.week <= week)
        next_topic = next((topic for topic in topics if topic.id not in done_ids), None)

        cards[key] = {
            "class_id": school_class.id,
            "class_name": class_name(school_class),
            "grade_number": school_class.grade_number,
            "subject_id": subject.id,
            "subject_name": subject.name,
            "teacher_name": teacher.full_name,
            "has_program": program is not None,
            "total": len(topics),
            "done": len(done_ids),
            # Пландагыдан канча тема артта калды (0 — план боюнча же алдыда)
            "behind": max(0, planned - len(done_ids)),
            "next_topic": next_topic.title if next_topic else None,
        }

    return {"current_week": week, "items": list(cards.values())}


# 2. Бир класстын бир предмет боюнча программасы жана прогресси
@router.get("/class/{class_id}/subject/{subject_id}")
def get_class_program(
    class_id: int,
    subject_id: int,
    current_user: Users = Depends(require_roles(*STAFF_ROLES)),
    db: Session = Depends(get_db),
):
    school_class = get_class_or_404(db, class_id, current_user.school_id)
    ensure_can_mark(db, current_user, class_id, subject_id)
    subject = db.query(Subjects).filter(
        Subjects.id == subject_id, Subjects.school_id == current_user.school_id
    ).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Предмет табылган жок")

    program = get_program(db, current_user.school_id, subject_id, school_class.grade_number)
    progress = {
        row.topic_id: row for row in db.query(CurriculumProgress).filter(
            CurriculumProgress.class_id == class_id
        )
    } if program else {}

    return {
        "class_id": school_class.id,
        "class_name": class_name(school_class),
        "grade_number": school_class.grade_number,
        "subject_id": subject.id,
        "subject_name": subject.name,
        "current_week": current_week(today_local()),
        "updated_at": program.updated_at if program else None,
        "topics": [
            {
                "id": topic.id,
                "position": topic.position,
                "section": topic.section,
                "title": topic.title,
                "hours": topic.hours,
                "week": topic.week,
                "goals": topic.goals,
                "materials": topic.materials,
                "done_on": progress[topic.id].done_on if topic.id in progress else None,
                "note": progress[topic.id].note if topic.id in progress else None,
            }
            for topic in (program.topics if program else [])
        ],
    }


# 3. Теманы «өтүлдү» деп белгилөө же белгини алуу (эскертме менен)
@router.put("/class/{class_id}/subject/{subject_id}/topics/{topic_id}")
def update_topic_progress(
    class_id: int,
    subject_id: int,
    topic_id: int,
    data: TopicProgressUpdate,
    current_user: Users = Depends(require_roles(*STAFF_ROLES)),
    db: Session = Depends(get_db),
):
    school_class = get_class_or_404(db, class_id, current_user.school_id)
    ensure_can_mark(db, current_user, class_id, subject_id)
    program = get_program(db, current_user.school_id, subject_id, school_class.grade_number)
    topic = db.query(CurriculumTopics).filter(
        CurriculumTopics.id == topic_id,
        CurriculumTopics.program_id == (program.id if program else None),
    ).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Тема табылган жок")

    row = db.query(CurriculumProgress).filter(
        CurriculumProgress.class_id == class_id, CurriculumProgress.topic_id == topic_id
    ).first()
    note = validate_free_text(data.note.strip()) if data.note and data.note.strip() else None

    if data.done:
        if row is None:
            row = CurriculumProgress(class_id=class_id, topic_id=topic_id, done_on=today_local())
            db.add(row)
        row.note = note
        row.marked_by = current_user.id
    elif row is not None:
        db.delete(row)

    db.commit()
    return {
        "topic_id": topic_id,
        "done_on": row.done_on if data.done else None,
        "note": note if data.done else None,
    }


def _cell(row: tuple, index: Optional[int]) -> str:
    if index is None or index >= len(row) or row[index] is None:
        return ""
    value = row[index]
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def _number(text: str, row_number: int, label: str, errors: list, maximum: int) -> Optional[int]:
    if not text:
        return None
    if not text.isdigit() or not 1 <= int(text) <= maximum:
        errors.append({"row": row_number, "error": f"{label}: 1ден {maximum}гө чейинки сан болушу керек"})
        return None
    return int(text)


# 4. Программаны Excel'ден жүктөө (мурунку темалар жана алардын прогресси алмаштырылат)
@router.post("/import")
async def import_program(
    subject_id: int = Form(...),
    grade_number: int = Form(..., ge=1, le=11),
    file: UploadFile = File(...),
    current_user: Users = Depends(require_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    subject = db.query(Subjects).filter(
        Subjects.id == subject_id, Subjects.school_id == current_user.school_id
    ).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Предмет табылган жок")

    content = await file.read(MAX_FILE_SIZE + 1)
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Файл 5 МБдан ашпашы керек")
    try:
        sheet = load_workbook(BytesIO(content), read_only=True, data_only=True).active
        rows = list(sheet.iter_rows(values_only=True))
    except Exception:
        raise HTTPException(status_code=400, detail="Excel файлын окуу мүмкүн болгон жок")

    if not rows:
        raise HTTPException(status_code=400, detail="Файл бош")

    headers = [str(value or "").strip().lower() for value in rows[0]]
    columns = {
        key: next((index for index, header in enumerate(headers) if header in names), None)
        for key, names in COLUMN_NAMES.items()
    }
    if columns["title"] is None:
        raise HTTPException(status_code=400, detail="Биринчи сапта «Тема» мамычасы болушу керек")

    topics, errors = [], []
    for row_number, row in enumerate(rows[1:], start=2):
        if not row or all(value is None or str(value).strip() == "" for value in row):
            continue
        title = _cell(row, columns["title"])
        if not title:
            errors.append({"row": row_number, "error": "Тема жазылган эмес"})
            continue
        try:
            section = validate_free_text(_cell(row, columns["section"])[:200]) or None
            title = validate_free_text(title[:300])
            goals = validate_free_text(_cell(row, columns["goals"])) or None
            materials = validate_free_text(_cell(row, columns["materials"])) or None
        except ValueError as error:
            errors.append({"row": row_number, "error": str(error)})
            continue
        hours = _number(_cell(row, columns["hours"]), row_number, "Саат", errors, 20) or 1
        week = _number(_cell(row, columns["week"]), row_number, "Апта", errors, 40)
        topics.append(dict(section=section, title=title, hours=hours, week=week, goals=goals, materials=materials))

    if errors:
        raise HTTPException(status_code=400, detail={"message": "Файлда каталар бар", "errors": errors})
    if not topics:
        raise HTTPException(status_code=400, detail="Файлда бир да тема жок")

    program = get_program(db, current_user.school_id, subject_id, grade_number)
    if program is None:
        program = CurriculumPrograms(
            school_id=current_user.school_id, subject_id=subject_id, grade_number=grade_number
        )
        db.add(program)
    else:
        program.topics.clear()
        program.updated_at = func.now()
    db.flush()

    for position, topic in enumerate(topics, start=1):
        program.topics.append(CurriculumTopics(position=position, **topic))

    db.commit()
    return {"subject_id": subject_id, "grade_number": grade_number, "topics_count": len(topics)}


# 5. Программаны өчүрүү
@router.delete("/subject/{subject_id}/grade/{grade_number}")
def delete_program(
    subject_id: int,
    grade_number: int,
    current_user: Users = Depends(require_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    program = get_program(db, current_user.school_id, subject_id, grade_number)
    if not program:
        raise HTTPException(status_code=404, detail="Программа табылган жок")
    db.delete(program)
    db.commit()
    return {"message": "Программа өчүрүлдү"}

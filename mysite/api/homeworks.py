"""Мультимедиа үй тапшырма модулу.

  * Мугалим өз сабагына тапшырма түзөт: текст + китеп беттеринин сүрөттөрү + PDF/документтер.
  * Окуучу жана ата-эне (баласынын) тапшырмаларын көрөт.
  * Окуучу тапшырманы аткарып, сүрөт/файл тиркеп тапшыра алат.
"""
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from mysite.db.database import get_db
from mysite.db.models import (
    Classes,
    HomeworkSubmissions,
    Homeworks,
    ParentStudents,
    StudentEnrollments,
    TeacherAssignments,
    Users,
)
from mysite.security.permissions import get_current_user, require_roles
from mysite.services.files import delete_media, is_image_url, save_upload
from mysite.services.notifications import notify
from mysite.services.school import (
    ADMIN_ROLES,
    TEACHER_ROLES,
    class_name,
    get_active_enrollment,
    get_assignment_or_404,
    is_class_teacher_of,
    is_parent_of,
    resolve_student_for_viewer,
)

router = APIRouter(prefix="/homeworks", tags=["Homeworks"])

MAX_FILES_PER_UPLOAD = 10


def serialize(hw: Homeworks, submission: Optional[HomeworkSubmissions] = None) -> dict:
    a = hw.assignment
    data = {
        "id": hw.id,
        "assignment_id": hw.assignment_id,
        "class_id": a.class_id,
        "class_name": class_name(a.school_class),
        "subject_id": a.subject_id,
        "subject_name": a.subject.name if a.subject else None,
        "teacher_id": a.teacher_id,
        "teacher_name": a.teacher.full_name if a.teacher else None,
        "title": hw.title,
        "description": hw.description,
        "image_urls": hw.image_urls or [],
        "file_urls": hw.file_urls or [],
        "due_date": hw.due_date,
        "created_at": hw.created_at,
    }
    if submission is not None:
        data["submission"] = serialize_submission(submission)
    return data


def serialize_submission(sub: HomeworkSubmissions) -> dict:
    return {
        "id": sub.id,
        "homework_id": sub.homework_id,
        "student_id": sub.student_id,
        "text": sub.text,
        "file_urls": sub.file_urls or [],
        "submitted_at": sub.submitted_at,
    }


def store_files(files: List[UploadFile], folder: str) -> tuple[list[str], list[str]]:
    files = [f for f in (files or []) if f is not None and f.filename]
    if len(files) > MAX_FILES_PER_UPLOAD:
        raise HTTPException(
            status_code=400,
            detail=f"Бир жолу эң көп {MAX_FILES_PER_UPLOAD} файл жүктөөгө болот",
        )
    images, documents = [], []
    for upload in files:
        url = save_upload(upload, folder)
        (images if is_image_url(url) else documents).append(url)
    return images, documents


def get_homework_or_404(db: Session, homework_id: int, school_id: int) -> Homeworks:
    hw = db.query(Homeworks).filter(
        Homeworks.id == homework_id,
        Homeworks.school_id == school_id,
    ).first()
    if hw is None:
        raise HTTPException(status_code=404, detail="Үй тапшырма табылган жок")
    return hw


def ensure_owner(user: Users, hw: Homeworks) -> None:
    if hw.assignment.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="Өз сабагыңыздын тапшырмасын гана өзгөртө аласыз")


def can_view_homework(db: Session, user: Users, hw: Homeworks) -> bool:
    class_id = hw.assignment.class_id
    if user.role in ADMIN_ROLES:
        return True
    if user.role in TEACHER_ROLES:
        return hw.assignment.teacher_id == user.id or is_class_teacher_of(
            user, hw.assignment.school_class
        )
    if user.role == "STUDENT":
        _, school_class = get_active_enrollment(db, user.id)
        return school_class is not None and school_class.id == class_id
    if user.role == "PARENT":
        child_ids = [
            link.student_id
            for link in db.query(ParentStudents).filter(ParentStudents.parent_id == user.id)
        ]
        return db.query(StudentEnrollments.id).filter(
            StudentEnrollments.student_id.in_(child_ids or [-1]),
            StudentEnrollments.class_id == class_id,
            StudentEnrollments.status == "ACTIVE",
        ).first() is not None
    return False


# =====================================================
# 1. Үй тапшырма түзүү (мугалим, өз сабагына)
# =====================================================

@router.post("", status_code=201)
def create_homework(
    assignment_id: int = Form(...),
    title: str = Form(..., min_length=2, max_length=200),
    description: Optional[str] = Form(default=None),
    due_date: Optional[date] = Form(default=None),
    files: List[UploadFile] = File(default=[]),
    current_user: Users = Depends(require_roles(*TEACHER_ROLES)),
    db: Session = Depends(get_db),
):
    assignment = get_assignment_or_404(db, assignment_id, current_user.school_id)
    if assignment.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="Сиз бул сабакка бекитилген эмессиз")

    images, documents = store_files(files, f"homeworks/{current_user.school_id}")

    hw = Homeworks(
        assignment_id=assignment.id,
        school_id=current_user.school_id,
        title=title.strip(),
        description=description,
        image_urls=images,
        file_urls=documents,
        due_date=due_date,
        created_by=current_user.id,
    )
    db.add(hw)
    db.flush()

    # Класстын окуучуларына жана ата-энелерине билдирүү
    student_ids = [
        e.student_id
        for e in db.query(StudentEnrollments).filter(
            StudentEnrollments.class_id == assignment.class_id,
            StudentEnrollments.status == "ACTIVE",
        )
    ]
    parent_ids = [
        link.parent_id
        for link in db.query(ParentStudents).filter(
            ParentStudents.student_id.in_(student_ids or [-1])
        )
    ]
    notify(
        db,
        student_ids + parent_ids,
        title=f"Жаңы үй тапшырма: {assignment.subject.name}",
        body=hw.title,
        link=f"/homeworks/{hw.id}",
    )

    db.commit()
    db.refresh(hw)
    return serialize(hw)


# =====================================================
# 2. Тапшырмалар тизмеси (ролго жараша)
# =====================================================

@router.get("")
def list_homeworks(
    student_id: Optional[int] = None,
    class_id: Optional[int] = None,
    subject_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    limit = max(1, min(limit, 200))
    query = (
        db.query(Homeworks)
        .join(TeacherAssignments, TeacherAssignments.id == Homeworks.assignment_id)
        .filter(Homeworks.school_id == current_user.school_id)
    )

    student = None
    if current_user.role in ("STUDENT", "PARENT"):
        student = resolve_student_for_viewer(db, current_user, student_id)
        _, school_class = get_active_enrollment(db, student.id)
        if school_class is None:
            return []
        query = query.filter(TeacherAssignments.class_id == school_class.id)

    elif current_user.role in TEACHER_ROLES:
        led = [c.id for c in db.query(Classes.id).filter(Classes.class_teacher_id == current_user.id)]
        query = query.filter(
            (TeacherAssignments.teacher_id == current_user.id)
            | (TeacherAssignments.class_id.in_(led or [-1]))
        )

    if class_id:
        query = query.filter(TeacherAssignments.class_id == class_id)
    if subject_id:
        query = query.filter(TeacherAssignments.subject_id == subject_id)
    if date_from:
        query = query.filter(Homeworks.created_at >= date_from)
    if date_to:
        query = query.filter(Homeworks.due_date <= date_to)

    homeworks = query.order_by(Homeworks.created_at.desc()).offset(offset).limit(limit).all()

    submissions = {}
    if student is not None and homeworks:
        submissions = {
            s.homework_id: s
            for s in db.query(HomeworkSubmissions).filter(
                HomeworkSubmissions.student_id == student.id,
                HomeworkSubmissions.homework_id.in_([h.id for h in homeworks]),
            )
        }

    result = []
    for hw in homeworks:
        item = serialize(hw, submissions.get(hw.id))
        if student is not None:
            item["is_submitted"] = hw.id in submissions
        result.append(item)
    return result


@router.get("/{homework_id}")
def get_homework(
    homework_id: int,
    student_id: Optional[int] = None,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    hw = get_homework_or_404(db, homework_id, current_user.school_id)
    if not can_view_homework(db, current_user, hw):
        raise HTTPException(status_code=403, detail="Бул тапшырманы көрүүгө уруксат жок")

    submission = None
    if current_user.role in ("STUDENT", "PARENT"):
        student = resolve_student_for_viewer(db, current_user, student_id)
        submission = db.query(HomeworkSubmissions).filter(
            HomeworkSubmissions.homework_id == hw.id,
            HomeworkSubmissions.student_id == student.id,
        ).first()

    data = serialize(hw, submission)
    if current_user.role in ("STUDENT", "PARENT"):
        data["is_submitted"] = submission is not None
    return data


# =====================================================
# 3. Өзгөртүү / файл кошуу / өчүрүү (ээси болгон мугалим)
# =====================================================

@router.put("/{homework_id}")
def update_homework(
    homework_id: int,
    title: Optional[str] = Form(default=None, min_length=2, max_length=200),
    description: Optional[str] = Form(default=None),
    due_date: Optional[date] = Form(default=None),
    current_user: Users = Depends(require_roles(*TEACHER_ROLES)),
    db: Session = Depends(get_db),
):
    hw = get_homework_or_404(db, homework_id, current_user.school_id)
    ensure_owner(current_user, hw)

    if title is not None:
        hw.title = title.strip()
    if description is not None:
        hw.description = description
    if due_date is not None:
        hw.due_date = due_date

    db.commit()
    db.refresh(hw)
    return serialize(hw)


@router.post("/{homework_id}/files")
def add_homework_files(
    homework_id: int,
    files: List[UploadFile] = File(...),
    current_user: Users = Depends(require_roles(*TEACHER_ROLES)),
    db: Session = Depends(get_db),
):
    hw = get_homework_or_404(db, homework_id, current_user.school_id)
    ensure_owner(current_user, hw)

    images, documents = store_files(files, f"homeworks/{current_user.school_id}")
    hw.image_urls = list(hw.image_urls or []) + images
    hw.file_urls = list(hw.file_urls or []) + documents

    db.commit()
    db.refresh(hw)
    return serialize(hw)


@router.delete("/{homework_id}/files")
def remove_homework_file(
    homework_id: int,
    url: str,
    current_user: Users = Depends(require_roles(*TEACHER_ROLES)),
    db: Session = Depends(get_db),
):
    hw = get_homework_or_404(db, homework_id, current_user.school_id)
    ensure_owner(current_user, hw)

    images = list(hw.image_urls or [])
    documents = list(hw.file_urls or [])
    if url in images:
        images.remove(url)
    elif url in documents:
        documents.remove(url)
    else:
        raise HTTPException(status_code=404, detail="Файл табылган жок")

    hw.image_urls, hw.file_urls = images, documents
    db.commit()
    delete_media(url)
    db.refresh(hw)
    return serialize(hw)


@router.delete("/{homework_id}")
def delete_homework(
    homework_id: int,
    current_user: Users = Depends(require_roles(*TEACHER_ROLES, *ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    hw = get_homework_or_404(db, homework_id, current_user.school_id)
    if current_user.role not in ADMIN_ROLES:
        ensure_owner(current_user, hw)

    urls = list(hw.image_urls or []) + list(hw.file_urls or [])
    for sub in hw.submissions:
        urls += list(sub.file_urls or [])

    db.delete(hw)
    db.commit()
    for url in urls:
        delete_media(url)
    return {"message": "Үй тапшырма өчүрүлдү"}


# =====================================================
# 4. Окуучу тапшырманы тапшырат
# =====================================================

@router.post("/{homework_id}/submit")
def submit_homework(
    homework_id: int,
    text: Optional[str] = Form(default=None),
    files: List[UploadFile] = File(default=[]),
    current_user: Users = Depends(require_roles("STUDENT")),
    db: Session = Depends(get_db),
):
    hw = get_homework_or_404(db, homework_id, current_user.school_id)
    if not can_view_homework(db, current_user, hw):
        raise HTTPException(status_code=403, detail="Бул тапшырма сиздин класска эмес")

    images, documents = store_files(files, f"submissions/{current_user.school_id}")
    new_urls = images + documents
    if not new_urls and not (text and text.strip()):
        raise HTTPException(status_code=400, detail="Текст же файл тиркеңиз")

    sub = db.query(HomeworkSubmissions).filter(
        HomeworkSubmissions.homework_id == hw.id,
        HomeworkSubmissions.student_id == current_user.id,
    ).first()

    if sub is None:
        sub = HomeworkSubmissions(
            homework_id=hw.id,
            student_id=current_user.id,
            text=text,
            file_urls=new_urls,
        )
        db.add(sub)
    else:
        if text is not None:
            sub.text = text
        sub.file_urls = list(sub.file_urls or []) + new_urls

    notify(
        db,
        hw.assignment.teacher_id,
        title="Үй тапшырма тапшырылды",
        body=f"{current_user.full_name}: {hw.title}",
        link=f"/homeworks/{hw.id}/submissions",
    )

    db.commit()
    db.refresh(sub)
    return serialize_submission(sub)


@router.get("/{homework_id}/submissions")
def list_submissions(
    homework_id: int,
    current_user: Users = Depends(require_roles(*TEACHER_ROLES, *ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    hw = get_homework_or_404(db, homework_id, current_user.school_id)
    if not can_view_homework(db, current_user, hw):
        raise HTTPException(status_code=403, detail="Уруксат жок")

    rows = (
        db.query(HomeworkSubmissions, Users)
        .join(Users, Users.id == HomeworkSubmissions.student_id)
        .filter(HomeworkSubmissions.homework_id == hw.id)
        .order_by(Users.full_name)
        .all()
    )
    return [
        {**serialize_submission(sub), "student_name": student.full_name}
        for sub, student in rows
    ]

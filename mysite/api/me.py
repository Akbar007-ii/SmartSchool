"""Жеке кабинет: профиль, аватар, сыр сөз, окуучунун профили (значоктору менен)."""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from mysite.api.ratings import student_standing
from mysite.db.database import get_db
from mysite.db.models import Classes, ParentStudents, Schools, TeacherAssignments, Users
from mysite.db.schema import PasswordChange, ProfileUpdate
from mysite.security.hashing import hash_password, verify_password
from mysite.security.permissions import get_current_user
from mysite.services.files import IMAGE_EXTENSIONS, delete_media, save_upload
from mysite.services.school import (
    ADMIN_ROLES,
    TEACHER_ROLES,
    class_name,
    ensure_can_view_student,
    get_active_enrollment,
    get_student_or_404,
)

router = APIRouter(tags=["Profile"])


def base_profile(user: Users) -> dict:
    return {
        "id": user.id,
        "inn": user.inn,
        "full_name": user.full_name,
        "role": user.role,
        "phone": user.phone,
        "avatar_url": user.avatar_url,
        "school_id": user.school_id,
        "is_temp_password": user.is_temp_password,
    }


@router.get("/me")
def get_me(
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = base_profile(current_user)

    school = db.query(Schools).filter(Schools.id == current_user.school_id).first()
    profile["school"] = {
        "id": school.id,
        "name": school.name,
        "address": school.address,
        "logo_url": school.logo_url,
        "banner_url": school.banner_url,
    } if school else None

    if current_user.role == "STUDENT":
        profile["student"] = student_standing(db, current_user)

    elif current_user.role == "PARENT":
        children = []
        for link in db.query(ParentStudents).filter(ParentStudents.parent_id == current_user.id):
            child = db.query(Users).filter(Users.id == link.student_id).first()
            if child is None:
                continue
            _, school_class = get_active_enrollment(db, child.id)
            children.append({
                "id": child.id,
                "full_name": child.full_name,
                "avatar_url": child.avatar_url,
                "class_id": school_class.id if school_class else None,
                "class_name": class_name(school_class),
            })
        profile["children"] = children

    elif current_user.role in TEACHER_ROLES:
        profile["classes_led"] = [
            {"id": c.id, "name": class_name(c), "academic_year": c.academic_year}
            for c in db.query(Classes).filter(Classes.class_teacher_id == current_user.id)
        ]
        profile["is_class_teacher"] = bool(profile["classes_led"])
        profile["assignments"] = [
            {
                "id": a.id,
                "class_id": a.class_id,
                "class_name": class_name(a.school_class),
                "subject_id": a.subject_id,
                "subject_name": a.subject.name,
                "academic_year": a.academic_year,
            }
            for a in db.query(TeacherAssignments).filter(
                TeacherAssignments.teacher_id == current_user.id
            )
        ]

    return profile


@router.put("/me")
def update_me(
    data: ProfileUpdate,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    update = data.model_dump(exclude_unset=True)

    # Аты-жөнүн окуучу өзү өзгөртө албайт (журналдагы расмий маалымат)
    if "full_name" in update and update["full_name"]:
        if current_user.role not in ADMIN_ROLES + ("PARENT",):
            raise HTTPException(
                status_code=403,
                detail="Аты-жөнүңүздү завуч гана өзгөртө алат",
            )
        current_user.full_name = update["full_name"].strip()

    if "phone" in update:
        current_user.phone = update["phone"]

    db.commit()
    db.refresh(current_user)
    return base_profile(current_user)


@router.post("/me/avatar")
def upload_avatar(
    file: UploadFile = File(...),
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    url = save_upload(file, f"avatars/{current_user.school_id}", allowed=IMAGE_EXTENSIONS)
    old = current_user.avatar_url
    current_user.avatar_url = url
    db.commit()
    delete_media(old)
    return {"avatar_url": url}


@router.post("/me/change-password")
def change_password(
    data: PasswordChange,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Учурдагы сыр сөз туура эмес")
    if data.current_password == data.new_password:
        raise HTTPException(status_code=400, detail="Жаңы сыр сөз эскисинен айырмаланышы керек")

    current_user.hashed_password = hash_password(data.new_password)
    current_user.is_temp_password = False
    current_user.temp_password_encrypted = None
    db.commit()
    return {"message": "Сыр сөз ийгиликтүү өзгөртүлдү"}


# Окуучунун профили: рейтингдеги орду, XP, таажы/медаль/чагылган/жылдыз
@router.get("/profiles/students/{student_id}")
def student_profile(
    student_id: int,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    student = get_student_or_404(db, student_id, current_user.school_id)

    # Рейтинг мектеп ичинде ачык, андыктан классташтар бири-биринин профилин көрө алат;
    # ал эми ата-эне өз баласыныкын гана көрөт.
    if current_user.role == "PARENT":
        ensure_can_view_student(db, current_user, student)

    return student_standing(db, student)

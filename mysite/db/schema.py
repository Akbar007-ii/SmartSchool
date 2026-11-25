
import re
from datetime import date, datetime, time
from enum import Enum
from typing import Optional, List, Literal

from pydantic import (BaseModel,ConfigDict,Field,field_validator,)

from mysite.services.text_checks import (
    validate_class_letter,
    validate_free_text,
    validate_person_name,
    validate_subject_name,
)

class UserRole(str, Enum):
    DIRECTOR = "DIRECTOR"
    DEPUTY = "DEPUTY"
    CLASS_TEACHER = "CLASS_TEACHER"
    TEACHER = "TEACHER"
    STUDENT = "STUDENT"
    PARENT = "PARENT"

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(value: str) -> str:
    """Почтаны текшерет жана кичине тамгаларга келтирет (логин катары колдонулат)."""
    email = value.strip().lower()
    if len(email) > 254 or not EMAIL_PATTERN.match(email):
        raise ValueError("Электрондук почта туура эмес")
    return email


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

class SchoolCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    email: Optional[str] = None
    logo_url: Optional[str] = None
    banner_url: Optional[str] = None
    director_name: Optional[str] = None

    @field_validator("name")
    @classmethod
    def check_names(cls, value):
        return value if value is None else validate_free_text(value)

    @field_validator("director_name")
    @classmethod
    def check_director_name(cls, value):
        return value if value is None else validate_person_name(value)


class SchoolUpdate(BaseModel):
    name: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=200
    )
    email: Optional[str] = None
    logo_url: Optional[str] = None
    banner_url: Optional[str] = None
    director_name: Optional[str] = None

    @field_validator("name")
    @classmethod
    def check_names(cls, value):
        return value if value is None else validate_free_text(value)

    @field_validator("director_name")
    @classmethod
    def check_director_name(cls, value):
        return value if value is None else validate_person_name(value)


class SchoolOut(BaseSchema):
    id: int
    name: str
    email: Optional[str]
    logo_url: Optional[str]
    banner_url: Optional[str]
    director_name: Optional[str]
    is_active: bool
    created_at: datetime

class UserCreate(BaseModel):
    email: str
    full_name: str = Field(min_length=3, max_length=200)
    role: UserRole
    password: str = Field(min_length=8)
    school_id: int

    @field_validator("full_name")
    @classmethod
    def check_full_name(cls, value):
        return value if value is None else validate_person_name(value)

    @field_validator("email")
    @classmethod
    def check_email(cls, value):
        return normalize_email(value)


class UserOut(BaseSchema):
    id: int
    email: str
    full_name: str
    role: UserRole
    avatar_url: Optional[str]
    school_id: int
    is_active: bool
    is_temp_password: bool
    created_at: datetime


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None

    @field_validator("full_name")
    @classmethod
    def check_full_name(cls, value):
        return value if value is None else validate_person_name(value)
    is_active: Optional[bool] = None

class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1)

    @field_validator("email")
    @classmethod
    def check_email(cls, value):
        return normalize_email(value)


class FirstLoginChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    requires_password_change: bool = False



class ClassCreate(BaseModel):
    grade_number: int = Field(ge=1, le=11)
    letter: str = Field(min_length=1, max_length=5)
    class_teacher_id: Optional[int] = None
    academic_year: str

    @field_validator("letter")
    @classmethod
    def check_letter(cls, value):
        return value if value is None else validate_class_letter(value)



class ClassOut(BaseSchema):
    id: int
    grade_number: int
    letter: str
    school_id: int
    class_teacher_id: Optional[int]
    academic_year: str



class SubjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)

    @field_validator("name")
    @classmethod
    def check_name(cls, value):
        return validate_subject_name(value)



class SubjectOut(BaseSchema):
    id: int
    name: str
    school_id: int


class TeacherAssignmentCreate(BaseModel):
    teacher_id: int
    class_id: int
    subject_id: int
    school_id: int
    academic_year: str


class TeacherAssignmentOut(BaseSchema):
    id: int
    teacher_id: int
    class_id: int
    subject_id: int
    school_id: int
    academic_year: str
    created_at: datetime


class TeacherCreate(BaseModel):
    email: str
    full_name: str = Field(min_length=3, max_length=200)

    @field_validator("full_name")
    @classmethod
    def check_full_name(cls, value):
        return value if value is None else validate_person_name(value)

    @field_validator("email")
    @classmethod
    def check_email(cls, value):
        return normalize_email(value)


class TeacherCreatedOut(BaseModel):
    id: int
    email: str
    full_name: str
    temporary_password: str
    role: str
    school_id: int

class StudentCreate(BaseModel):
    email: str
    full_name: str = Field(min_length=3, max_length=200)

    @field_validator("full_name")
    @classmethod
    def check_full_name(cls, value):
        return value if value is None else validate_person_name(value)
    class_id: int

    @field_validator("email")
    @classmethod
    def check_email(cls, value):
        return normalize_email(value)

class StudentPromotionRequest(BaseModel):
    source_academic_year: str = Field(
        min_length=9,
        max_length=20
    )

    target_academic_year: str = Field(
        min_length=9,
        max_length=20
    )

    excluded_student_ids: List[int] = Field(default_factory=list)


class StudentPromotionMove(BaseModel):
    # Автоматтык өткөрүүдөн кийин окуучуну кийинки окуу жылынын башка классына которуу
    student_id: int
    target_academic_year: str = Field(min_length=9, max_length=20)
    grade_number: int = Field(ge=1, le=11)
    letter: str = Field(min_length=1, max_length=5)

    @field_validator("letter")
    @classmethod
    def check_letter(cls, value):
        return validate_class_letter(value)

class StudentUpdate(BaseModel):
    full_name: Optional[str] = Field(
        default=None,
        min_length=3,
        max_length=200
    )
    email: Optional[str] = None

    @field_validator("email")
    @classmethod
    def check_email(cls, value):
        return value if value is None else normalize_email(value)

    @field_validator("full_name")
    @classmethod
    def check_full_name(cls, value):
        return value if value is None else validate_person_name(value)



def normalize_parent_code(value: str) -> str:
    """Ата-эне коду: «k7p2-mx4q» → «K7P2MX4Q» (дефис жана боштуктар маанилүү эмес)."""
    code = "".join(value.split()).replace("-", "").upper()
    if not 6 <= len(code) <= 12 or not code.isalnum():
        raise ValueError("Код туура эмес")
    return code


class ParentRegister(BaseModel):
    email: str
    full_name: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=8)

    @field_validator("full_name")
    @classmethod
    def check_full_name(cls, value):
        return value if value is None else validate_person_name(value)

    student_code: str

    @field_validator("email")
    @classmethod
    def check_email(cls, value):
        return normalize_email(value)

    @field_validator("student_code")
    @classmethod
    def check_code(cls, value):
        return normalize_parent_code(value)


class ParentLinkStudent(BaseModel):
    student_email: str
    student_temporary_password: str = Field(min_length=1)
    relationship_type: Optional[str] = None

    @field_validator("student_email")
    @classmethod
    def check_email(cls, value):
        return normalize_email(value)

class ParentAddChild(BaseModel):
    student_code: str

    @field_validator("student_code")
    @classmethod
    def check_code(cls, value):
        return normalize_parent_code(value)


class ForgotPassword(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def check_email(cls, value):
        return normalize_email(value)


class ResetPassword(BaseModel):
    token: str = Field(min_length=10)
    new_password: str = Field(min_length=8, max_length=128)

class ClassTeacherAssign(BaseModel):
    teacher_id: Optional[int] = None


# =====================================================
# Мугалимди сабакка байлоо (ТЗ: POST /admin/teacher-assignments)
# =====================================================

class AdminTeacherAssignmentCreate(BaseModel):
    teacher_id: int
    class_id: int
    subject_id: int
    # Берилбесе класстын окуу жылы алынат
    academic_year: Optional[str] = None


# =====================================================
# Электрондук журнал
# =====================================================

AttendanceCode = Literal["Б", "Ж", "С", "К"]


class JournalEntryIn(BaseModel):
    student_id: int
    grade_value: Optional[int] = Field(default=None, ge=2, le=5)
    attendance: Optional[AttendanceCode] = None
    comment: Optional[str] = Field(default=None, max_length=500)

    @field_validator("comment")
    @classmethod
    def check_comment(cls, value):
        return value if value is None else validate_free_text(value)


class JournalSave(BaseModel):
    assignment_id: int
    date: date
    entries: List[JournalEntryIn] = Field(min_length=1)


# Чейректер (Q1–Q4) жана жылдык баа (YEAR)
PeriodCode = Literal["Q1", "Q2", "Q3", "Q4", "YEAR"]


class PeriodGradeIn(BaseModel):
    student_id: int
    # null — жыйынтык бааны өчүрүү
    grade_value: Optional[int] = Field(default=None, ge=2, le=5)


class PeriodGradesSave(BaseModel):
    assignment_id: int
    period: PeriodCode
    entries: List[PeriodGradeIn] = Field(min_length=1)


# =====================================================
# Сабактан сурануу (ата-эне гана жөнөтөт)
# =====================================================

class AbsenceRequestCreate(BaseModel):
    # Ата-эненин бир гана баласы болсо, көрсөтпөсө да болот
    student_id: Optional[int] = None
    # Берилбесе — бүгүнкү күн
    target_date: Optional[date] = None
    reason: str = Field(min_length=2, max_length=100)
    comment: Optional[str] = Field(default=None, max_length=1000)

    @field_validator("reason", "comment")
    @classmethod
    def check_text(cls, value):
        return value if value is None else validate_free_text(value)


class AbsenceReview(BaseModel):
    comment: Optional[str] = Field(default=None, max_length=500)

    @field_validator("comment")
    @classmethod
    def check_comment(cls, value):
        return value if value is None else validate_free_text(value)


# =====================================================
# Олимпиада
# =====================================================

class OlympiadCandidateCreate(BaseModel):
    subject_id: int
    student_id: int
    note: Optional[str] = Field(default=None, max_length=500)

    @field_validator("note")
    @classmethod
    def check_note(cls, value):
        return value if value is None else validate_free_text(value)


class OlympiadAutoSelect(BaseModel):
    subject_id: int
    grade_number: Optional[int] = Field(default=None, ge=1, le=11)
    limit: int = Field(default=3, ge=1, le=20)


# =====================================================
# Профиль
# =====================================================

class BannerPosition(BaseModel):
    url: str = Field(max_length=500)
    x: float = Field(ge=0, le=100)
    y: float = Field(ge=0, le=100)


class ProfileUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=3, max_length=200)
    email_notifications: Optional[bool] = None
    # null — баннер кайра ортого
    banner_position: Optional[BannerPosition] = None

    @field_validator("full_name")
    @classmethod
    def check_full_name(cls, value):
        return value if value is None else validate_person_name(value)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=128)


# =====================================================
# Мугалимдерди жана предметтерди өзгөртүү
# =====================================================

class TeacherUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=3, max_length=200)
    email: Optional[str] = None

    @field_validator("email")
    @classmethod
    def check_email(cls, value):
        return value if value is None else normalize_email(value)

    @field_validator("full_name")
    @classmethod
    def check_full_name(cls, value):
        return value if value is None else validate_person_name(value)


# =====================================================
# Сабактардын жадыбалы
# =====================================================

class ScheduleLessonCreate(BaseModel):
    # Класс жана мугалим+предмет ушул бекитүүдөн алынат
    assignment_id: int
    weekday: int = Field(ge=1, le=6, description="1 = дүйшөмбү ... 6 = ишемби")
    lesson_number: int = Field(ge=1, le=10)
    # Берилбесе, коңгуроолордун демейки жадыбалынан алынат (GET /schedule/bells)
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    room: Optional[str] = Field(default=None, max_length=50)

    @field_validator("room")
    @classmethod
    def check_room(cls, value):
        return value if value is None else validate_free_text(value)


class ScheduleLessonUpdate(BaseModel):
    assignment_id: Optional[int] = None
    weekday: Optional[int] = Field(default=None, ge=1, le=6)
    lesson_number: Optional[int] = Field(default=None, ge=1, le=10)
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    room: Optional[str] = Field(default=None, max_length=50)

    @field_validator("room")
    @classmethod
    def check_room(cls, value):
        return value if value is None else validate_free_text(value)


# =====================================================
# Платформанын администратору (SYSTEM_ADMIN) жана мектеп жетекчилери
# =====================================================

class SchoolAdminCreate(BaseModel):
    email: str
    full_name: str = Field(min_length=3, max_length=200)

    @field_validator("full_name")
    @classmethod
    def check_full_name(cls, value):
        return value if value is None else validate_person_name(value)

    @field_validator("email")
    @classmethod
    def check_email(cls, value):
        return normalize_email(value)


class SchoolAdminUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=3, max_length=200)
    email: Optional[str] = None

    @field_validator("email")
    @classmethod
    def check_email(cls, value):
        return value if value is None else normalize_email(value)

    @field_validator("full_name")
    @classmethod
    def check_full_name(cls, value):
        return value if value is None else validate_person_name(value)


class SchoolAdminWithRole(SchoolAdminCreate):
    role: Literal["DIRECTOR", "DEPUTY"] = "DIRECTOR"


class SystemSchoolCreate(SchoolCreate):
    # Мектеп түзүлөрү менен анын директору да түзүлөт
    director: SchoolAdminCreate


class SubjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=100)

    @field_validator("name")
    @classmethod
    def check_name(cls, value):
        return value if value is None else validate_subject_name(value)

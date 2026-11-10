
from datetime import datetime
from enum import Enum
from typing import Optional,List

from pydantic import (BaseModel,ConfigDict,Field,field_validator,)

class UserRole(str, Enum):
    DIRECTOR = "DIRECTOR"
    DEPUTY = "DEPUTY"
    CLASS_TEACHER = "CLASS_TEACHER"
    TEACHER = "TEACHER"
    STUDENT = "STUDENT"
    PARENT = "PARENT"

class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

class SchoolCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    logo_url: Optional[str] = None
    banner_url: Optional[str] = None
    director_name: Optional[str] = None


class SchoolUpdate(BaseModel):
    name: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=200
    )
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    logo_url: Optional[str] = None
    banner_url: Optional[str] = None
    director_name: Optional[str] = None


class SchoolOut(BaseSchema):
    id: int
    name: str
    address: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    logo_url: Optional[str]
    banner_url: Optional[str]
    director_name: Optional[str]
    is_active: bool
    created_at: datetime

class UserCreate(BaseModel):
    inn: str
    full_name: str = Field(min_length=3, max_length=200)
    role: UserRole
    password: str = Field(min_length=8)
    phone: Optional[str] = None
    school_id: int

    @field_validator("inn")
    @classmethod
    def validate_inn(cls, value):
        if not value.isdigit() or len(value) != 14:
            raise ValueError("ИНН 14 цифрадан турушу керек")
        return value


class UserOut(BaseSchema):
    id: int
    inn: str
    full_name: str
    role: UserRole
    phone: Optional[str]
    avatar_url: Optional[str]
    school_id: int
    is_active: bool
    is_temp_password: bool
    created_at: datetime


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: Optional[bool] = None

class LoginRequest(BaseModel):
    inn: str = Field(min_length=14, max_length=14)
    password: str = Field(min_length=1)

    @field_validator("inn")
    @classmethod
    def validate_inn(cls, value):
        if not value.isdigit():
            raise ValueError("ИНН 14 цифрадан турушу керек")
        return value


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



class ClassOut(BaseSchema):
    id: int
    grade_number: int
    letter: str
    school_id: int
    class_teacher_id: Optional[int]
    academic_year: str



class SubjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    code: Optional[str] = None



class SubjectOut(BaseSchema):
    id: int
    name: str
    code: Optional[str]
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
    inn: str
    full_name: str = Field(min_length=3, max_length=200)
    phone: Optional[str] = None

    @field_validator("inn")
    @classmethod
    def validate_inn(cls, value):
        if not value.isdigit() or len(value) != 14:
            raise ValueError("ИНН 14 цифра болушу керек")
        return value


class TeacherCreatedOut(BaseModel):
    id: int
    inn: str
    full_name: str
    temporary_password: str
    role: str
    school_id: int

class StudentCreate(BaseModel):
    inn: str = Field(min_length=14, max_length=14)
    full_name: str = Field(min_length=3, max_length=200)
    phone: Optional[str] = None
    class_id: int

    @field_validator("inn")
    @classmethod
    def validate_inn(cls, value):
        if not value.isdigit() or len(value) != 14:
            raise ValueError("ИНН 14 цифра болушу керек")
        return value

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

class StudentUpdate(BaseModel):
    full_name: Optional[str] = Field(
        default=None,
        min_length=3,
        max_length=200
    )

    phone: Optional[str] = Field(
        default=None,
        max_length=20
    )



class ParentRegister(BaseModel):
    inn: str = Field(min_length=14, max_length=14)
    full_name: str = Field(min_length=3, max_length=200)
    phone: Optional[str] = Field(default=None, max_length=20)
    password: str = Field(min_length=8)

    student_inn: str = Field(min_length=14, max_length=14)
    student_password: str = Field(min_length=1)

    @field_validator("inn")
    @classmethod
    def validate_inn(cls, value):
        if not value.isdigit():
            raise ValueError("ИНН 14 цифра болушу керек")
        return value


class ParentLinkStudent(BaseModel):
    student_inn: str = Field(min_length=14, max_length=14)
    student_temporary_password: str = Field(min_length=1)
    relationship_type: Optional[str] = None

    @field_validator("student_inn")
    @classmethod
    def validate_student_inn(cls, value):
        if not value.isdigit():
            raise ValueError("ИНН 14 цифра болушу керек")
        return value

class ParentAddChild(BaseModel):
    student_inn: str = Field(min_length=14, max_length=14)
    student_password: str = Field(min_length=1)

class ClassTeacherAssign(BaseModel):
    teacher_id: Optional[int] = None
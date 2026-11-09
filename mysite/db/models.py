from datetime import datetime
from typing import List, Optional
from sqlalchemy import (Integer,String,Boolean,DateTime,ForeignKey,UniqueConstraint,CheckConstraint,func,)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

class Schools(Base):
    __tablename__ = "schools"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[Optional[str]] = mapped_column(String(300))
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    email: Mapped[Optional[str]] = mapped_column(String(100))
    logo_url: Mapped[Optional[str]] = mapped_column(String(500))
    banner_url: Mapped[Optional[str]] = mapped_column(String(500))
    director_name: Mapped[Optional[str]] = mapped_column(String(150))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    users: Mapped[List["Users"]] = relationship(back_populates="school")
    classes: Mapped[List["Classes"]] = relationship(back_populates="school")
    subjects: Mapped[List["Subjects"]] = relationship(back_populates="school")
    teacher_assignments: Mapped[List["TeacherAssignments"]] = relationship(back_populates="school")


class Users(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    inn: Mapped[str] = mapped_column(String(14), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_temp_password: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500))
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id"), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    school: Mapped["Schools"] = relationship(back_populates="users")

    classes_led: Mapped[List["Classes"]] = relationship(back_populates="class_teacher",foreign_keys="Classes.class_teacher_id")

    teacher_assignments: Mapped[List["TeacherAssignments"]] = relationship(back_populates="teacher",foreign_keys="TeacherAssignments.teacher_id")

    __table_args__ = (
        CheckConstraint(
            "inn ~ '^[0-9]{14}$'",
            name="check_inn_format"
        ),
        CheckConstraint(
            "role IN ('DIRECTOR', 'DEPUTY', 'CLASS_TEACHER', "
            "'TEACHER', 'STUDENT', 'PARENT')",
            name="check_user_role"
        ),
    )


class Classes(Base):
    __tablename__ = "classes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    grade_number: Mapped[int] = mapped_column(Integer, nullable=False)
    letter: Mapped[str] = mapped_column(String(5), nullable=False)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id"), nullable=False, index=True)
    class_teacher_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    academic_year: Mapped[str] = mapped_column(String(20), nullable=False)

    school: Mapped["Schools"] = relationship(back_populates="classes")

    class_teacher: Mapped[Optional["Users"]] = relationship(back_populates="classes_led",
                                                            foreign_keys=[class_teacher_id])

    teacher_assignments: Mapped[List["TeacherAssignments"]] = relationship(
        back_populates="school_class")

    __table_args__ = (
        CheckConstraint(
            "grade_number >= 1 AND grade_number <= 11",
            name="check_grade_number"
        ),
        UniqueConstraint(
            "school_id",
            "grade_number",
            "letter",
            "academic_year",
            name="unique_school_class"
        ),
    )

class Subjects(Base):
    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[Optional[str]] = mapped_column(String(30))
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id"), nullable=False, index=True)
    school: Mapped["Schools"] = relationship(back_populates="subjects")
    teacher_assignments: Mapped[List["TeacherAssignments"]] = relationship(back_populates="subject")

    __table_args__ = (
        UniqueConstraint(
            "school_id",
            "name",
            name="unique_school_subject"
        ),
    )


class TeacherAssignments(Base):
    __tablename__ = "teacher_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"), nullable=False)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"), nullable=False)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id"), nullable=False, index=True)
    academic_year: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    teacher: Mapped["Users"] = relationship(back_populates="teacher_assignments")
    school_class: Mapped["Classes"] = relationship(back_populates="teacher_assignments")
    subject: Mapped["Subjects"] = relationship(back_populates="teacher_assignments")
    school: Mapped["Schools"] = relationship(back_populates="teacher_assignments")

    __table_args__ = (
        UniqueConstraint(
            "teacher_id",
            "class_id",
            "subject_id",
            "academic_year",
            name="unique_teacher_assignment"
        ),
    )

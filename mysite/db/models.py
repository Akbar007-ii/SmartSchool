
from datetime import datetime
from typing import List, Optional

from datetime import date as dt_date

from sqlalchemy import (
    JSON,
    Date,
    Text,
    Integer,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    CheckConstraint,
    func,
    Index
)

from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship
)

from .database import Base


# =====================================================
# 1. SCHOOLS
# =====================================================

class Schools(Base):
    __tablename__ = "schools"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False
    )

    address: Mapped[Optional[str]] = mapped_column(String(300))
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    email: Mapped[Optional[str]] = mapped_column(String(100))
    logo_url: Mapped[Optional[str]] = mapped_column(String(500))
    banner_url: Mapped[Optional[str]] = mapped_column(String(500))
    director_name: Mapped[Optional[str]] = mapped_column(String(150))

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    users: Mapped[List["Users"]] = relationship(
        back_populates="school"
    )

    classes: Mapped[List["Classes"]] = relationship(
        back_populates="school"
    )

    subjects: Mapped[List["Subjects"]] = relationship(
        back_populates="school"
    )

    teacher_assignments: Mapped[List["TeacherAssignments"]] = relationship(
        back_populates="school"
    )


# =====================================================
# 2. USERS
# =====================================================

class Users(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    inn: Mapped[str] = mapped_column(
        String(14),
        unique=True,
        nullable=False,
        index=True
    )

    full_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False
    )

    role: Mapped[str] = mapped_column(
        String(30),
        nullable=False
    )

    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    is_temp_password: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )

    phone: Mapped[Optional[str]] = mapped_column(String(20))

    avatar_url: Mapped[Optional[str]] = mapped_column(String(500))

    # Убактылуу сыр сөз шифрленген түрдө (Fernet) гана сакталат жана
    # колдонуучу биринчи жолу сыр сөзүн алмаштырганда өчүрүлөт.
    temp_password_encrypted: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True
    )

    school_id: Mapped[int] = mapped_column(
        ForeignKey("schools.id"),
        nullable=False,
        index=True
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    school: Mapped["Schools"] = relationship(
        back_populates="users"
    )

    # Класс жетекчи болгон класстар
    classes_led: Mapped[List["Classes"]] = relationship(
        back_populates="class_teacher",
        foreign_keys="Classes.class_teacher_id"
    )

    # Мугалимдин предметтик бекитүүлөрү
    teacher_assignments: Mapped[List["TeacherAssignments"]] = relationship(
        back_populates="teacher",
        foreign_keys="TeacherAssignments.teacher_id"
    )

    # Окуучунун класстарга катталуусу
    student_enrollments: Mapped[List["StudentEnrollments"]] = relationship(
        back_populates="student",
        foreign_keys="StudentEnrollments.student_id"
    )

    # Ата-эне болгон байланыштар
    children_links: Mapped[List["ParentStudents"]] = relationship(
        back_populates="parent",
        foreign_keys="ParentStudents.parent_id",
        cascade="all, delete-orphan"
    )

    # Ата-энеси байланыштырылган окуучунун байланыштары
    parent_links: Mapped[List["ParentStudents"]] = relationship(
        back_populates="student",
        foreign_keys="ParentStudents.student_id"
    )

    __table_args__ = (
        CheckConstraint(
            "inn ~ '^[0-9]{14}$'",
            name="check_inn_format"
        ),

        CheckConstraint(
            "role IN ('SYSTEM_ADMIN','DIRECTOR', 'DEPUTY', 'CLASS_TEACHER', "
            "'TEACHER', 'STUDENT', 'PARENT')",
            name="check_user_role"
        ),
    )


# =====================================================
# 3. CLASSES
# =====================================================

class Classes(Base):
    __tablename__ = "classes"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    grade_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    letter: Mapped[str] = mapped_column(
        String(5),
        nullable=False
    )

    school_id: Mapped[int] = mapped_column(
        ForeignKey("schools.id"),
        nullable=False,
        index=True
    )

    class_teacher_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"),
        nullable=True
    )

    academic_year: Mapped[str] = mapped_column(
        String(20),
        nullable=False
    )

    school: Mapped["Schools"] = relationship(
        back_populates="classes"
    )

    class_teacher: Mapped[Optional["Users"]] = relationship(
        back_populates="classes_led",
        foreign_keys=[class_teacher_id]
    )

    teacher_assignments: Mapped[List["TeacherAssignments"]] = relationship(
        back_populates="school_class"
    )

    student_enrollments: Mapped[List["StudentEnrollments"]] = relationship(
        back_populates="school_class"
    )

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

        Index(
            "ix_classes_school_academic_year",
            "school_id",
            "academic_year"
        ),
    )


# =====================================================
# 4. SUBJECTS
# =====================================================

class Subjects(Base):
    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    code: Mapped[Optional[str]] = mapped_column(
        String(30)
    )

    school_id: Mapped[int] = mapped_column(
        ForeignKey("schools.id"),
        nullable=False,
        index=True
    )

    school: Mapped["Schools"] = relationship(
        back_populates="subjects"
    )

    teacher_assignments: Mapped[List["TeacherAssignments"]] = relationship(
        back_populates="subject"
    )

    __table_args__ = (
        UniqueConstraint(
            "school_id",
            "name",
            name="unique_school_subject"
        ),
    )


# =====================================================
# 5. TEACHER ASSIGNMENTS
# =====================================================

class TeacherAssignments(Base):
    __tablename__ = "teacher_assignments"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    class_id: Mapped[int] = mapped_column(
        ForeignKey("classes.id"),
        nullable=False,
        index=True
    )

    subject_id: Mapped[int] = mapped_column(
        ForeignKey("subjects.id"),
        nullable=False,
        index=True
    )

    school_id: Mapped[int] = mapped_column(
        ForeignKey("schools.id"),
        nullable=False,
        index=True
    )

    academic_year: Mapped[str] = mapped_column(
        String(20),
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    teacher: Mapped["Users"] = relationship(
        back_populates="teacher_assignments"
    )

    school_class: Mapped["Classes"] = relationship(
        back_populates="teacher_assignments"
    )

    subject: Mapped["Subjects"] = relationship(
        back_populates="teacher_assignments"
    )

    school: Mapped["Schools"] = relationship(
        back_populates="teacher_assignments"
    )

    __table_args__ = (
        UniqueConstraint(
            "teacher_id",
            "class_id",
            "subject_id",
            "academic_year",
            name="unique_teacher_assignment"
        ),

        Index(
            "ix_teacher_assignments_school_year",
            "school_id",
            "academic_year"
        ),
    )


# =====================================================
# 6. STUDENT ENROLLMENTS
# =====================================================

class StudentEnrollments(Base):
    __tablename__ = "student_enrollments"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    student_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    class_id: Mapped[int] = mapped_column(
        ForeignKey("classes.id"),
        nullable=False,
        index=True
    )

    academic_year: Mapped[str] = mapped_column(
        String(20),
        nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="ACTIVE",
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    student: Mapped["Users"] = relationship(
        back_populates="student_enrollments",
        foreign_keys=[student_id]
    )

    school_class: Mapped["Classes"] = relationship(
        back_populates="student_enrollments"
    )

    __table_args__ = (
        UniqueConstraint(
            "student_id",
            "academic_year",
            name="unique_student_academic_year"
        ),

        CheckConstraint(
            "status IN ('ACTIVE', 'COMPLETED', 'TRANSFERRED')",
            name="check_enrollment_status"
        ),
    )


# =====================================================
# 7. PARENT STUDENTS
# =====================================================

class ParentStudents(Base):
    __tablename__ = "parent_students"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    parent_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    student_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    relationship_type: Mapped[Optional[str]] = mapped_column(
        String(30),
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    parent: Mapped["Users"] = relationship(
        back_populates="children_links",
        foreign_keys=[parent_id]
    )

    student: Mapped["Users"] = relationship(
        back_populates="parent_links",
        foreign_keys=[student_id]
    )

    __table_args__ = (
        UniqueConstraint(
            "student_id",
            name="unique_student_parent"
        ),
        CheckConstraint(
            "parent_id != student_id",
            name="check_parent_not_student"
        ),
    )


# =====================================================
# 8. JOURNAL ENTRIES (grades) — электрондук журнал
# =====================================================
# Бир сабак (assignment) + бир окуучу + бир күн = бир жазуу.
# grade_value: 2..5 (же NULL), attendance: 'Б' (бар), 'Ж' (себепсиз жок),
# 'С' (себептүү — сурануу бекитилген), 'К' (кечикти).

class JournalEntries(Base):
    __tablename__ = "grades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    assignment_id: Mapped[int] = mapped_column(
        ForeignKey("teacher_assignments.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    student_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )

    school_id: Mapped[int] = mapped_column(
        ForeignKey("schools.id"), nullable=False, index=True
    )

    date: Mapped[dt_date] = mapped_column(Date, nullable=False, index=True)

    grade_value: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    attendance: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)

    comment: Mapped[Optional[str]] = mapped_column(String(500))

    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    assignment: Mapped["TeacherAssignments"] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "assignment_id", "student_id", "date",
            name="unique_journal_entry"
        ),
        CheckConstraint(
            "grade_value IS NULL OR (grade_value >= 2 AND grade_value <= 5)",
            name="check_grade_value"
        ),
        CheckConstraint(
            "attendance IS NULL OR attendance IN ('Б', 'Ж', 'С', 'К')",
            name="check_attendance"
        ),
        Index("ix_grades_student_date", "student_id", "date"),
    )


# =====================================================
# 9. SUBJECT XP — предметтик рейтинг
# =====================================================

class SubjectXP(Base):
    __tablename__ = "subject_xp"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    student_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )

    subject_id: Mapped[int] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    school_id: Mapped[int] = mapped_column(
        ForeignKey("schools.id"), nullable=False, index=True
    )

    current_xp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    rank_position: Mapped[Optional[int]] = mapped_column(Integer)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("student_id", "subject_id", name="unique_student_subject_xp"),
    )


# =====================================================
# 10. ABSENCE REQUESTS — сабактан сурануу
# =====================================================
# Сурануу ата-эне тарабынан ГАНА жөнөтүлөт (окуучуга уруксат жок).

class AbsenceRequests(Base):
    __tablename__ = "absence_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    student_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )

    parent_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )

    class_id: Mapped[int] = mapped_column(
        ForeignKey("classes.id"), nullable=False, index=True
    )

    school_id: Mapped[int] = mapped_column(
        ForeignKey("schools.id"), nullable=False, index=True
    )

    target_date: Mapped[dt_date] = mapped_column(Date, nullable=False, index=True)

    reason: Mapped[str] = mapped_column(String(100), nullable=False)

    comment: Mapped[Optional[str]] = mapped_column(String(1000))

    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False)

    request_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    reviewed_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))

    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    review_comment: Mapped[Optional[str]] = mapped_column(String(500))

    student: Mapped["Users"] = relationship(foreign_keys=[student_id])
    parent: Mapped["Users"] = relationship(foreign_keys=[parent_id])
    school_class: Mapped["Classes"] = relationship()

    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED', 'CANCELLED')",
            name="check_absence_status"
        ),
        Index("ix_absence_student_date", "student_id", "target_date"),
    )


# =====================================================
# 11. HOMEWORKS — мультимедиа үй тапшырма
# =====================================================

class Homeworks(Base):
    __tablename__ = "homeworks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    assignment_id: Mapped[int] = mapped_column(
        ForeignKey("teacher_assignments.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    school_id: Mapped[int] = mapped_column(
        ForeignKey("schools.id"), nullable=False, index=True
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)

    description: Mapped[Optional[str]] = mapped_column(Text)

    image_urls: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    file_urls: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    due_date: Mapped[Optional[dt_date]] = mapped_column(Date)

    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    assignment: Mapped["TeacherAssignments"] = relationship()

    submissions: Mapped[List["HomeworkSubmissions"]] = relationship(
        back_populates="homework",
        cascade="all, delete-orphan"
    )


class HomeworkSubmissions(Base):
    __tablename__ = "homework_submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    homework_id: Mapped[int] = mapped_column(
        ForeignKey("homeworks.id", ondelete="CASCADE"), nullable=False, index=True
    )

    student_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )

    text: Mapped[Optional[str]] = mapped_column(Text)

    file_urls: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    homework: Mapped["Homeworks"] = relationship(back_populates="submissions")

    __table_args__ = (
        UniqueConstraint("homework_id", "student_id", name="unique_homework_submission"),
    )


# =====================================================
# 12. USER BADGES — таажылар жана значоктор
# =====================================================

class UserBadges(Base):
    __tablename__ = "user_badges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )

    badge_type: Mapped[str] = mapped_column(String(30), nullable=False)

    # SUBJECT_LEADER жана OLYMPIAD_CANDIDATE үчүн — кайсы предмет
    subject_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE")
    )

    icon_name: Mapped[str] = mapped_column(String(50), nullable=False)

    awarded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "badge_type IN ('SUBJECT_LEADER', 'PARALLEL_CHAMP', "
            "'PERFECT_ATTENDANCE', 'OLYMPIAD_CANDIDATE')",
            name="check_badge_type"
        ),
    )


# =====================================================
# 13. OLYMPIAD CANDIDATES
# =====================================================

class OlympiadCandidates(Base):
    __tablename__ = "olympiad_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    school_id: Mapped[int] = mapped_column(
        ForeignKey("schools.id"), nullable=False, index=True
    )

    subject_id: Mapped[int] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False
    )

    student_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    academic_year: Mapped[str] = mapped_column(String(20), nullable=False)

    # SUGGESTED — мугалим сунуштаган, SELECTED — завуч/директор тандаган
    status: Mapped[str] = mapped_column(String(20), default="SUGGESTED", nullable=False)

    suggested_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))

    approved_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))

    note: Mapped[Optional[str]] = mapped_column(String(500))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "subject_id", "student_id", "academic_year",
            name="unique_olympiad_candidate"
        ),
        CheckConstraint(
            "status IN ('SUGGESTED', 'SELECTED')",
            name="check_olympiad_status"
        ),
    )


# =====================================================
# 14. ANNOUNCEMENTS — жарыялар
# =====================================================

class Announcements(Base):
    __tablename__ = "announcements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    school_id: Mapped[int] = mapped_column(
        ForeignKey("schools.id"), nullable=False, index=True
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)

    body: Mapped[Optional[str]] = mapped_column(Text)

    image_url: Mapped[Optional[str]] = mapped_column(String(500))

    event_date: Mapped[Optional[dt_date]] = mapped_column(Date)

    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# =====================================================
# 15. NOTIFICATIONS — билдирүүлөр (🔔)
# =====================================================

class Notifications(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)

    body: Mapped[Optional[str]] = mapped_column(String(1000))

    link: Mapped[Optional[str]] = mapped_column(String(300))

    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


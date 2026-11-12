"""Геймификация кыймылдаткычы: XP эсептөө, рейтингдер жана значоктор (ТЗ 4-бөлүм).

XP эрежелери (ТЗ 4.2):
    Баа 5 -> +50, 4 -> +30, 3 -> +10, 2 -> -20, катышуу «Б» -> +5.
Ар бир упай окуучунун предметтик XP'сине кошулат, жалпы XP = предметтик XP'лердин суммасы.

XP журналдагы жазуулардан ар дайым кайра эсептелет (инкременттик эмес),
ошондуктан баа өзгөртүлсө же өчүрүлсө да упайлар туура бойдон калат.
"""
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Optional

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from mysite.db.models import (
    Classes,
    JournalEntries,
    OlympiadCandidates,
    StudentEnrollments,
    SubjectXP,
    TeacherAssignments,
    UserBadges,
    Users,
)

GRADE_XP = {5: 50, 4: 30, 3: 10, 2: -20}
ATTENDANCE_XP = {"Б": 5}

BADGE_ICONS = {
    "SUBJECT_LEADER": "crown",           # Алтын таажы
    "PARALLEL_CHAMP": "medal",           # Алтын медаль
    "PERFECT_ATTENDANCE": "lightning",   # Чагылган
    "OLYMPIAD_CANDIDATE": "star",        # Жылдыз
}

OLYMPIAD_TOP_N = 3


def entry_xp(grade_value: Optional[int], attendance: Optional[str]) -> int:
    return GRADE_XP.get(grade_value or 0, 0) + ATTENDANCE_XP.get(attendance or "", 0)


def _xp_sql_expr():
    grade_part = case(
        *[(JournalEntries.grade_value == g, xp) for g, xp in GRADE_XP.items()],
        else_=0,
    )
    attendance_part = case(
        *[(JournalEntries.attendance == a, xp) for a, xp in ATTENDANCE_XP.items()],
        else_=0,
    )
    return grade_part + attendance_part


# =====================================================
# XP кайра эсептөө
# =====================================================

def recompute_subject_xp(
    db: Session, school_id: int, pairs: Iterable[tuple[int, int]]
) -> None:
    """(student_id, subject_id) жуптары үчүн subject_xp таблицасын жаңыртат."""
    pairs = set(pairs)
    if not pairs:
        return

    xp_expr = _xp_sql_expr()
    subjects = {subject_id for _, subject_id in pairs}

    for student_id, subject_id in pairs:
        total = (
            db.query(func.coalesce(func.sum(xp_expr), 0))
            .join(TeacherAssignments, TeacherAssignments.id == JournalEntries.assignment_id)
            .filter(
                JournalEntries.student_id == student_id,
                TeacherAssignments.subject_id == subject_id,
            )
            .scalar()
        )

        row = db.query(SubjectXP).filter(
            SubjectXP.student_id == student_id,
            SubjectXP.subject_id == subject_id,
        ).first()

        if row is None:
            row = SubjectXP(
                student_id=student_id,
                subject_id=subject_id,
                school_id=school_id,
                current_xp=int(total),
            )
            db.add(row)
        else:
            row.current_xp = int(total)

    db.flush()

    # Мектеп боюнча предметтик орундарды жаңыртуу
    for subject_id in subjects:
        rows = db.query(SubjectXP).filter(
            SubjectXP.school_id == school_id,
            SubjectXP.subject_id == subject_id,
        ).order_by(SubjectXP.current_xp.desc(), SubjectXP.student_id).all()
        _assign_ranks(rows, key=lambda r: r.current_xp, setter=lambda r, p: setattr(r, "rank_position", p))

    db.flush()


def _assign_ranks(items, key, setter):
    """Стандарттык рейтинг (1, 2, 2, 4): бирдей упайга бирдей орун."""
    position = 0
    previous = object()
    for index, item in enumerate(items, start=1):
        value = key(item)
        if value != previous:
            position = index
            previous = value
        setter(item, position)


# =====================================================
# Рейтинг маалыматтары
# =====================================================

@dataclass
class StudentScore:
    student_id: int
    full_name: str
    avatar_url: Optional[str]
    class_id: int
    class_name: str
    grade_number: int
    subject_xp: dict = field(default_factory=dict)

    @property
    def total_xp(self) -> int:
        return sum(self.subject_xp.values())


def load_scores(db: Session, school_id: int) -> list[StudentScore]:
    """Мектептин бардык активдүү окуучулары жана алардын предметтик XP'лери."""
    rows = (
        db.query(Users, Classes)
        .join(StudentEnrollments, StudentEnrollments.student_id == Users.id)
        .join(Classes, Classes.id == StudentEnrollments.class_id)
        .filter(
            Users.school_id == school_id,
            Users.role == "STUDENT",
            Users.is_active.is_(True),
            StudentEnrollments.status == "ACTIVE",
            Classes.school_id == school_id,
        )
        .all()
    )

    scores: dict[int, StudentScore] = {}
    for user, school_class in rows:
        scores[user.id] = StudentScore(
            student_id=user.id,
            full_name=user.full_name,
            avatar_url=user.avatar_url,
            class_id=school_class.id,
            class_name=f"{school_class.grade_number}-{school_class.letter}",
            grade_number=school_class.grade_number,
        )

    for xp in db.query(SubjectXP).filter(SubjectXP.school_id == school_id).all():
        if xp.student_id in scores:
            scores[xp.student_id].subject_xp[xp.subject_id] = xp.current_xp

    return list(scores.values())


def rank(
    scores: list[StudentScore],
    subject_id: Optional[int] = None,
    class_id: Optional[int] = None,
    grade_number: Optional[int] = None,
) -> list[dict]:
    """Фильтрленген жана орундары коюлган рейтинг тизмеси."""
    items = [
        s for s in scores
        if (class_id is None or s.class_id == class_id)
        and (grade_number is None or s.grade_number == grade_number)
    ]

    def xp_of(s: StudentScore) -> int:
        return s.subject_xp.get(subject_id, 0) if subject_id else s.total_xp

    items.sort(key=lambda s: (-xp_of(s), s.full_name))

    result = [
        {
            "rank": 0,
            "student_id": s.student_id,
            "full_name": s.full_name,
            "avatar_url": s.avatar_url,
            "class_id": s.class_id,
            "class_name": s.class_name,
            "xp": xp_of(s),
        }
        for s in items
    ]
    _assign_ranks(result, key=lambda r: r["xp"], setter=lambda r, p: r.__setitem__("rank", p))
    return result


# =====================================================
# Значоктор (Badges & Crowns) — ТЗ 4.3
# =====================================================

def compute_badges(db: Session, school_id: int) -> dict[int, set[tuple[str, Optional[int]]]]:
    scores = load_scores(db, school_id)
    badges: dict[int, set[tuple[str, Optional[int]]]] = defaultdict(set)

    subject_ids = {sid for s in scores for sid in s.subject_xp}
    grades = {s.grade_number for s in scores}

    # Алтын таажы — предмет боюнча мектепте же параллелде 1-орун
    for subject_id in subject_ids:
        scopes = [rank(scores, subject_id=subject_id)] + [
            rank(scores, subject_id=subject_id, grade_number=g) for g in grades
        ]
        for ranking in scopes:
            for row in ranking:
                if row["rank"] == 1 and row["xp"] > 0:
                    badges[row["student_id"]].add(("SUBJECT_LEADER", subject_id))

        # Жылдыз — предмет боюнча мектепте Топ-3
        for row in rank(scores, subject_id=subject_id):
            if row["rank"] <= OLYMPIAD_TOP_N and row["xp"] > 0:
                badges[row["student_id"]].add(("OLYMPIAD_CANDIDATE", subject_id))

    # Завуч тандаган олимпиадалык курам
    for candidate in db.query(OlympiadCandidates).filter(
        OlympiadCandidates.school_id == school_id,
        OlympiadCandidates.status == "SELECTED",
    ).all():
        badges[candidate.student_id].add(("OLYMPIAD_CANDIDATE", candidate.subject_id))

    # Алтын медаль — параллелдин чемпиону (жалпы XP боюнча)
    for g in grades:
        for row in rank(scores, grade_number=g):
            if row["rank"] == 1 and row["xp"] > 0:
                badges[row["student_id"]].add(("PARALLEL_CHAMP", None))

    # Чагылган — бир да себепсиз калбаган жана кечикпеген окуучу
    attendance_rows = (
        db.query(
            JournalEntries.student_id,
            func.count(JournalEntries.attendance),
            func.sum(case((JournalEntries.attendance.in_(["Ж", "К"]), 1), else_=0)),
        )
        .filter(JournalEntries.school_id == school_id)
        .group_by(JournalEntries.student_id)
        .all()
    )
    active_ids = {s.student_id for s in scores}
    for student_id, marked, bad in attendance_rows:
        if student_id in active_ids and marked and not bad:
            badges[student_id].add(("PERFECT_ATTENDANCE", None))

    return badges


def sync_badges(db: Session, school_id: int) -> None:
    """user_badges таблицасын эсептелген абалга шайкештейт."""
    wanted = compute_badges(db, school_id)

    existing = (
        db.query(UserBadges)
        .join(Users, Users.id == UserBadges.user_id)
        .filter(Users.school_id == school_id)
        .all()
    )

    existing_keys = set()
    for badge in existing:
        key = (badge.badge_type, badge.subject_id)
        if key in wanted.get(badge.user_id, set()):
            existing_keys.add((badge.user_id, *key))
        else:
            db.delete(badge)

    for user_id, keys in wanted.items():
        for badge_type, subject_id in keys:
            if (user_id, badge_type, subject_id) not in existing_keys:
                db.add(UserBadges(
                    user_id=user_id,
                    badge_type=badge_type,
                    subject_id=subject_id,
                    icon_name=BADGE_ICONS[badge_type],
                ))

    db.flush()

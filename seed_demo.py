"""Фронтенд иштеп чыгуу үчүн демо-маалыматтар.

    python seed_demo.py
    docker compose exec api python seed_demo.py

Бир демо-мектеп түзөт: директор, 2 мугалим (бири класс жетекчи), 2 класс,
3 предмет, 6 окуучу, ата-эне, акыркы 2 жумалык журнал, үй тапшырма, жарыя,
каралбаган сурануу. Бардык демо-аккаунттардын сыр сөзү: Demo#2026
(убактылуу эмес — биринчи кирүүдө алмаштыруу талап кылынбайт).

Демо мектеп мурда түзүлгөн болсо, скрипт эч нерсе кылбайт.
"""
import random
import sys
from datetime import timedelta

from mysite.db.database import SessionLocal
from mysite.db.models import (
    AbsenceRequests,
    Announcements,
    Classes,
    Homeworks,
    JournalEntries,
    ParentStudents,
    Schools,
    StudentEnrollments,
    Subjects,
    TeacherAssignments,
    Users,
)
from mysite.security.hashing import hash_password
from mysite.services.rating import recompute_subject_xp, sync_badges
from mysite.services.timeutils import current_academic_year, now_local

DEMO_PASSWORD = "Demo#2026"
DEMO_SCHOOL = "Smart School №1 (Демо)"

random.seed(2026)
db = SessionLocal()

if db.query(Schools).filter(Schools.name == DEMO_SCHOOL).first():
    sys.exit("Демо мектеп мурда эле түзүлгөн — эч нерсе өзгөргөн жок.")

if db.query(Users).filter(Users.inn.like("100000000000%")).first():
    sys.exit("КАТА: демо ИНН номерлери (100000000000xx) мурда эле колдонулган.")

password_hash = hash_password(DEMO_PASSWORD)
year = current_academic_year()
today = now_local().date()
accounts = []


def user(inn, name, role, school_id):
    u = Users(inn=inn, full_name=name, role=role, hashed_password=password_hash,
              is_temp_password=False, school_id=school_id)
    db.add(u)
    db.flush()
    accounts.append((role, inn, name))
    return u


try:
    school = Schools(
        name=DEMO_SCHOOL,
        address="Бишкек ш., Ч.Айтматов көч. 25",
        phone="+996700123456",
        email="demo@smartschool.kg",
        director_name="Асанов Бакыт",
    )
    db.add(school)
    db.flush()

    director = user("10000000000001", "Асанов Бакыт", "DIRECTOR", school.id)
    teacher_kg = user("10000000000010", "Иванова Мария Петровна", "TEACHER", school.id)
    teacher_math = user("10000000000011", "Сапарова Гүлнара", "TEACHER", school.id)

    class_a = Classes(grade_number=11, letter="А", school_id=school.id,
                      class_teacher_id=teacher_kg.id, academic_year=year)
    class_b = Classes(grade_number=11, letter="Б", school_id=school.id,
                      class_teacher_id=teacher_math.id, academic_year=year)
    db.add_all([class_a, class_b])
    db.flush()

    subjects = {}
    for name, code in (("Кыргыз тили", "KG"), ("Математика", "MATH"), ("Физика", "PHYS")):
        subject = Subjects(name=name, code=code, school_id=school.id)
        db.add(subject)
        db.flush()
        subjects[name] = subject

    assignments = []
    for school_class in (class_a, class_b):
        for subject_name, teacher in (
            ("Кыргыз тили", teacher_kg),
            ("Математика", teacher_math),
            ("Физика", teacher_math),
        ):
            a = TeacherAssignments(teacher_id=teacher.id, class_id=school_class.id,
                                   subject_id=subjects[subject_name].id,
                                   school_id=school.id, academic_year=year)
            db.add(a)
            assignments.append(a)
    db.flush()

    students = {}
    for inn, name, school_class in (
        ("10000000000101", "Алиев Эркин", class_a),
        ("10000000000102", "Токтосунов Бекзат", class_a),
        ("10000000000103", "Жумабекова Айдана", class_a),
        ("10000000000104", "Касымов Нурлан", class_b),
        ("10000000000105", "Жолдошев Адилет", class_b),
        ("10000000000106", "Кадырова Айназик", class_b),
    ):
        s = user(inn, name, "STUDENT", school.id)
        db.add(StudentEnrollments(student_id=s.id, class_id=school_class.id,
                                  academic_year=year, status="ACTIVE"))
        students[s.id] = (s, school_class)

    parent = user("10000000000201", "Алиева Назира", "PARENT", school.id)
    erkin = next(s for s, _ in students.values() if s.inn == "10000000000101")
    aidana = next(s for s, _ in students.values() if s.inn == "10000000000103")
    db.add_all([
        ParentStudents(parent_id=parent.id, student_id=erkin.id, relationship_type="Апасы"),
        ParentStudents(parent_id=parent.id, student_id=aidana.id, relationship_type="Апасы"),
    ])

    # Акыркы 14 күндүн иш күндөрүндөгү журнал
    pairs = set()
    for days_ago in range(14, 0, -1):
        day = today - timedelta(days=days_ago)
        if day.weekday() >= 5:
            continue
        for a in assignments:
            for student, school_class in students.values():
                if school_class.id != a.class_id:
                    continue
                attendance = random.choices(["Б", "Ж", "К"], weights=[90, 4, 6])[0]
                grade = None
                if attendance != "Ж" and random.random() < 0.35:
                    grade = random.choices([5, 4, 3, 2], weights=[40, 35, 20, 5])[0]
                db.add(JournalEntries(assignment_id=a.id, student_id=student.id,
                                      school_id=school.id, date=day, grade_value=grade,
                                      attendance=attendance, created_by=a.teacher_id))
                pairs.add((student.id, a.subject_id))
    db.flush()
    recompute_subject_xp(db, school.id, pairs)
    sync_badges(db, school.id)

    kg_a = next(a for a in assignments
                if a.class_id == class_a.id and a.subject_id == subjects["Кыргыз тили"].id)
    db.add(Homeworks(assignment_id=kg_a.id, school_id=school.id,
                     title="№234, 235, 236 көнүгүүлөр",
                     description="Китептин 45-бетиндеги эрежени жаттап, көнүгүүлөрдү аткаргыла.",
                     image_urls=[], file_urls=[], due_date=today + timedelta(days=2),
                     created_by=teacher_kg.id))

    db.add(Announcements(school_id=school.id, title="Республикалык олимпиада",
                         body="Кыргыз тили боюнча олимпиада өтөт. Талапкерлер рейтинг боюнча тандалат.",
                         event_date=today + timedelta(days=10), created_by=director.id))

    db.add(AbsenceRequests(student_id=erkin.id, parent_id=parent.id, class_id=class_a.id,
                           school_id=school.id, target_date=today + timedelta(days=1),
                           reason="Оору", comment="Дарыгерге барабыз", status="PENDING",
                           request_time=now_local()))

    db.commit()

except Exception as error:
    db.rollback()
    sys.exit(f"КАТА: {error}")

finally:
    db.close()

print(f"Демо мектеп түзүлдү: {DEMO_SCHOOL} (окуу жылы {year})")
print(f"Бардык аккаунттардын сыр сөзү: {DEMO_PASSWORD}\n")
print(f"{'Ролу':<10} {'Логин (ИНН)':<16} Аты-жөнү")
for role, inn, name in accounts:
    print(f"{role:<10} {inn:<16} {name}")
print("\nИванова М.П. — 11-А, Сапарова Г. — 11-Б класс жетекчиси.")
print("Алиева Назира — Эркин менен Айдананын ата-энеси.")

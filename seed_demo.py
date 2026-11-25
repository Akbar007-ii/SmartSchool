"""Фронтенд иштеп чыгуу үчүн демо-маалыматтар.

    python seed_demo.py
    docker compose exec api python seed_demo.py

Бир демо-мектеп түзөт: директор, завуч, 2 мугалим (бири класс жетекчи), 2 класс,
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
    CurriculumPrograms,
    CurriculumProgress,
    CurriculumTopics,
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
from mysite.services.accounts import new_parent_code
from mysite.services.rating import recompute_subject_xp, sync_badges
from mysite.services.timeutils import current_academic_year, now_local

DEMO_PASSWORD = "Demo#2026"
DEMO_SCHOOL = "Smart School №1 (Демо)"

random.seed(2026)
db = SessionLocal()

if db.query(Schools).filter(Schools.name == DEMO_SCHOOL).first():
    sys.exit("Демо мектеп мурда эле түзүлгөн — эч нерсе өзгөргөн жок.")

if db.query(Users).filter(Users.email.like("%@demo.kg")).first():
    sys.exit("КАТА: демо почталары (@demo.kg) мурда эле колдонулган.")

password_hash = hash_password(DEMO_PASSWORD)
year = current_academic_year()
today = now_local().date()
accounts = []


def user(email, name, role, school_id):
    u = Users(email=email, full_name=name, role=role, hashed_password=password_hash,
              is_temp_password=False, school_id=school_id)
    db.add(u)
    db.flush()
    accounts.append((role, email, name))
    return u


try:
    school = Schools(
        name=DEMO_SCHOOL,
        email="demo@smartschool.kg",
        director_name="Асанов Бакыт",
    )
    db.add(school)
    db.flush()

    director = user("director@demo.kg", "Асанов Бакыт", "DIRECTOR", school.id)
    user("deputy@demo.kg", "Сыдыкова Айгүл", "DEPUTY", school.id)
    teacher_kg = user("teacher.kg@demo.kg", "Иванова Мария Петровна", "TEACHER", school.id)
    teacher_math = user("teacher.math@demo.kg", "Сапарова Гүлнара", "TEACHER", school.id)

    class_a = Classes(grade_number=11, letter="А", school_id=school.id,
                      class_teacher_id=teacher_kg.id, academic_year=year)
    class_b = Classes(grade_number=11, letter="Б", school_id=school.id,
                      class_teacher_id=teacher_math.id, academic_year=year)
    # 9-А — окуучуларды кийинки класска которууну көрсөтүү үчүн (11-класстар бүтүрүп кетет)
    class_c = Classes(grade_number=9, letter="А", school_id=school.id,
                      class_teacher_id=None, academic_year=year)
    db.add_all([class_a, class_b, class_c])
    db.flush()

    subjects = {}
    for name in ("Кыргыз тили", "Математика", "Физика"):
        subject = Subjects(name=name, school_id=school.id)
        db.add(subject)
        db.flush()
        subjects[name] = subject

    assignments = []
    for school_class in (class_a, class_b, class_c):
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

    # Окуу программасы: Математика, 11-класс (11-Б классында биринчи темалар өтүлгөн)
    math_program = CurriculumPrograms(school_id=school.id, subject_id=subjects["Математика"].id, grade_number=11)
    db.add(math_program)
    for position, (section, title, hours, week, goals, materials) in enumerate((
        ("Кайталоо", "10-класстын материалын кайталоо", 2, 1, "Негизги формулаларды эстейт", None),
        ("Туунду", "Функциянын туундусу", 3, 2, "Туундунун аныктамасын түшүнөт", "Окуу китеби, 5–12-беттер"),
        ("Туунду", "Туундуларды эсептөө эрежелери", 3, 3, "Суммадан, көбөйтүндүдөн туунду алат", None),
        ("Туунду", "Туундунун геометриялык мааниси", 2, 5, "Жаныманын теңдемесин түзөт", None),
        ("Туундунун колдонулушу", "Функциянын өсүшү жана кемиши", 3, 6, "Монотондуулук аралыктарын табат", None),
        ("Туундунун колдонулушу", "Экстремумдар", 3, 8, "Максимум жана минимум чекиттерин табат", None),
        ("Интеграл", "Баштапкы функция", 2, 10, "Баштапкы функцияны табат", None),
        ("Интеграл", "Аныкталган интеграл", 3, 12, "Аянтты интеграл менен эсептейт", None),
    ), start=1):
        math_program.topics.append(CurriculumTopics(
            position=position, section=section, title=title, hours=hours,
            week=week, goals=goals, materials=materials,
        ))
    db.flush()
    for topic in math_program.topics[:3]:
        db.add(CurriculumProgress(class_id=class_b.id, topic_id=topic.id,
                                  done_on=today - timedelta(days=30 - topic.position * 7),
                                  marked_by=teacher_math.id))

    students = {}
    for email, name, school_class in (
        ("erkin@demo.kg", "Алиев Эркин", class_a),
        ("bekzat@demo.kg", "Токтосунов Бекзат", class_a),
        ("aidana@demo.kg", "Жумабекова Айдана", class_a),
        ("nurlan@demo.kg", "Касымов Нурлан", class_b),
        ("adilet@demo.kg", "Жолдошев Адилет", class_b),
        ("ainazik@demo.kg", "Кадырова Айназик", class_b),
        ("timur@demo.kg", "Осмонов Тимур", class_c),
        ("saltanat@demo.kg", "Бекова Салтанат", class_c),
        ("ermek@demo.kg", "Усенов Эрмек", class_c),
    ):
        s = user(email, name, "STUDENT", school.id)
        s.parent_code = new_parent_code(db)
        db.add(StudentEnrollments(student_id=s.id, class_id=school_class.id,
                                  academic_year=year, status="ACTIVE"))
        students[s.id] = (s, school_class)

    parent = user("parent@demo.kg", "Алиева Назира", "PARENT", school.id)
    erkin = next(s for s, _ in students.values() if s.email == "erkin@demo.kg")
    aidana = next(s for s, _ in students.values() if s.email == "aidana@demo.kg")
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
print(f"{'Ролу':<10} {'Логин (почта)':<22} Аты-жөнү")
for role, email, name in accounts:
    print(f"{role:<10} {email:<22} {name}")
print("\nИванова М.П. — 11-А, Сапарова Г. — 11-Б класс жетекчиси.")
print("Алиева Назира — Эркин менен Айдананын ата-энеси.")

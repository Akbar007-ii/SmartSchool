"""Postman коллекциясын жана тест файлдарын түзөт.

    python postman/build_collection.py

Натыйжа:
    postman/SmartSchool.postman_collection.json   — Postman'га импорттолот
    postman/files/*                               — жүктөлүүчү Excel/сүрөт/PDF файлдар
"""
import json
import re
from pathlib import Path

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parent
FILES = ROOT / "files"
FILES.mkdir(exist_ok=True)

# ---------- тест файлдары ----------

def excel(name, rows):
    wb = Workbook()
    ws = wb.active
    ws.append(["ИНН", "Толук аты-жөнү", "Телефон"])
    for row in rows:
        ws.append(row)
    wb.save(FILES / name)


excel("teachers_admin.xlsx", [["90000000000011", "Экинчи Мугалим", "+996700000011"]])
excel("teachers_router.xlsx", [["90000000000012", "Үчүнчү Мугалим", None]])
excel("teachers_users.xlsx", [["90000000000013", "Төртүнчү Мугалим", None]])
excel("students_11a.xlsx", [
    ["90000000000101", "Алиев Эркин", "+996700000101"],
    ["90000000000102", "Токтосунов Бекзат", None],
    ["90000000000103", "Жумабекова Айдана", None],
])
excel("students_5b.xlsx", [["90000000000104", "Касымов Нурлан", None]])
(FILES / "page.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
(FILES / "extra.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x01" * 64)
(FILES / "formula.pdf").write_bytes(b"%PDF-1.4\n% Smart School test\n")

# ---------- коллекцияны куруу ----------

folders = []
current = None
counter = 0


def folder(name):
    global current
    current = {"name": name, "item": []}
    folders.append(current)


def req(name, method, path, token=None, body=None, form=None, files=None,
        expect=200, tests=""):
    """expect: статус код же JS туюнтма (мис: "pm.variables.get('x') ? 201 : 403")."""
    global counter
    counter += 1

    raw_path, _, query = path.partition("?")
    url = {
        "raw": "{{base_url}}" + path,
        "host": ["{{base_url}}"],
        "path": [p for p in raw_path.split("/") if p] + ([""] if raw_path.endswith("/") and raw_path != "/" else []),
    }
    if query:
        url["query"] = [
            {"key": kv.partition("=")[0], "value": kv.partition("=")[2]}
            for kv in query.split("&")
        ]

    request = {"method": method, "header": [], "url": url}
    if token:
        request["header"].append(
            {"key": "Authorization", "value": "Bearer {{%s}}" % token}
        )

    if body is not None:
        request["body"] = {
            "mode": "raw",
            "raw": body if isinstance(body, str) else json.dumps(body, ensure_ascii=False, indent=2),
            "options": {"raw": {"language": "json"}},
        }
    elif form is not None or files is not None:
        formdata = [{"key": k, "value": v, "type": "text"} for k, v in (form or {}).items()]
        formdata += [{"key": k, "type": "file", "src": f"files/{v}"} for k, v in (files or [])]
        request["body"] = {"mode": "formdata", "formdata": formdata}

    expected = str(expect)
    script = [
        f"const expected = {expected};",
        "pm.test('Статус ' + expected, () => pm.response.to.have.status(expected));",
        "let res = null;",
        "try { res = pm.response.json(); } catch (e) {}",
    ] + [
        # `data` — Postman sandbox'тун резервделген аты, ошондуктан `res` колдонулат
        re.sub(r"\bdata\b", "res", line)
        for line in tests.strip().splitlines() if line.strip()
    ]

    current["item"].append({
        "name": f"{counter:03d}. {name}",
        "request": request,
        "event": [{"listen": "test", "script": {"type": "text/javascript", "exec": script}}],
    })


def save(var, expr):
    return f"if (pm.response.code < 300) pm.collectionVariables.set('{var}', {expr});"


def check(title, expr):
    return f"pm.test({json.dumps(title, ensure_ascii=False)}, () => pm.expect({expr}).to.be.true);"


NEW_PW = "NewPass#2026"


def login_flow(label, inn, pw_var, token_var):
    req(f"{label}: убактылуу сыр сөз менен кирүү", "POST", "/auth/login",
        body='{"inn": "%s", "password": "{{%s}}"}' % (inn, pw_var),
        tests=save("tmp_token", "data.access_token")
        + "\n" + check("Сыр сөздү алмаштыруу талап кылынат", "data.requires_password_change === true"))
    req(f"{label}: биринчи кирүүдө сыр сөздү алмаштыруу", "POST", "/auth/first-login-change",
        token="tmp_token",
        body='{"current_password": "{{%s}}", "new_password": "%s"}' % (pw_var, NEW_PW),
        tests=save(token_var, "data.access_token"))


# ============ 1. Ачык портал ============
folder("01. Ачык портал (авторизациясыз)")
req("API иштеп жатат", "GET", "/")
req("Платформанын статистикасы", "GET", "/public/stats",
    tests=check("Мектептер бар", "data.schools >= 1"))
req("Мектептердин тизмеси (издөө)", "GET", "/public/schools?search=Postman",
    tests=check("Мектеп табылды", "data.length >= 1"))

# ============ 2. Авторизация ============
folder("02. Авторизация жана директордун профили")
req("Ката сыр сөз -> 401", "POST", "/auth/login",
    body={"inn": "90000000000001", "password": "wrong-password"}, expect=401)
req("Токенсиз суроо -> 401", "GET", "/me", expect=401)
pm_director_pw = "director_pw"
login_flow("Директор", "90000000000001", pm_director_pw, "director")
req("Башка мектептин директору кирет", "POST", "/auth/login",
    body={"inn": "90000000000002", "password": "Mektep#2026"},
    tests=save("other_director", "data.access_token"))
req("Сервердин абалы (health)", "GET", "/health", tests=check("status ok", "data.status === 'ok'"))
req("Менин профилим", "GET", "/me", token="director",
    tests=save("school_id", "data.school_id") + "\n" + check("Ролу DIRECTOR", "data.role === 'DIRECTOR'"))
req("Профилди жаңыртуу", "PUT", "/me", token="director", body={"phone": "+996700000001"})
req("Мектептин маалыматы", "GET", "/schools/me", token="director")
req("Мектепти өзгөртүү", "PUT", "/schools/me", token="director",
    body={"address": "Бишкек ш., Ч.Айтматов көч. 25", "phone": "+996700123456", "director_name": "Тест Директор"})
req("Баннер жүктөө", "POST", "/schools/me/banner", token="director", files=[("file", "page.png")],
    tests=check("banner_url коюлду", "data.banner_url.endsWith('.png')"))
req("Логотип жүктөө", "POST", "/schools/me/logo", token="director", files=[("file", "extra.png")])
req("Мектептин ачык баракчасы", "GET", "/public/schools/{{school_id}}",
    tests=check("Баннери бар", "!!data.banner_url"))

# ============ 3. Класстар жана предметтер ============
folder("03. Класстар жана предметтер")
req("11-А классын түзүү", "POST", "/classes/", token="director",
    body={"grade_number": 11, "letter": "А", "academic_year": "2026-2027"},
    tests=save("class_id", "data.id"))
req("5-Б классын түзүү", "POST", "/classes/", token="director",
    body={"grade_number": 5, "letter": "Б", "academic_year": "2026-2027"},
    tests=save("class2_id", "data.id"))
req("Убактылуу класс түзүү", "POST", "/classes/", token="director",
    body={"grade_number": 1, "letter": "В", "academic_year": "2026-2027"},
    tests=save("class3_id", "data.id"))
req("Кайталанган класс -> 400", "POST", "/classes/", token="director",
    body={"grade_number": 11, "letter": "А", "academic_year": "2026-2027"}, expect=400)
req("Класстардын тизмеси", "GET", "/classes/", token="director",
    tests=check("3 класс", "data.length === 3"))
req("Бир класс", "GET", "/classes/{{class_id}}", token="director")
req("Классты өзгөртүү", "PUT", "/classes/{{class3_id}}", token="director",
    body={"grade_number": 1, "letter": "Г", "academic_year": "2026-2027"})
req("Классты өчүрүү", "DELETE", "/classes/{{class3_id}}", token="director")
req("Предмет: Кыргыз тили", "POST", "/subjects/", token="director",
    body={"name": "Кыргыз тили", "code": "KG"}, tests=save("subject_id", "data.id"))
req("Предмет: Математика", "POST", "/subjects/", token="director",
    body={"name": "Математика", "code": "MATH"}, tests=save("subject2_id", "data.id"))
req("Предметтердин тизмеси", "GET", "/subjects/", token="director")
req("Бир предмет", "GET", "/subjects/{{subject_id}}", token="director")

# ============ 4. Мугалимдер ============
folder("04. Мугалимдер, Excel жана бекитүүлөр")
req("Мугалимди бирден кошуу", "POST", "/users/create-teacher", token="director",
    body={"inn": "90000000000010", "full_name": "Класс Жетекчи Мугалим", "phone": "+996700000010"},
    tests=save("teacher_id", "data.id") + "\n" + save("teacher_pw", "data.temporary_password"))
req("Excel үлгүсү: мугалимдер", "GET", "/admin/excel/templates/teachers", token="director")
req("Excel: мугалимдерди жүктөө (ТЗ дареги)", "POST", "/admin/excel/import-teachers", token="director",
    files=[("file", "teachers_admin.xlsx")],
    tests=check("1 мугалим кошулду", "data.total_added === 1")
    + "\n" + save("teacher2_pw", "data.added_teachers[0].temporary_password"))
req("Excel: /teachers/import-excel", "POST", "/teachers/import-excel", token="director",
    files=[("file", "teachers_router.xlsx")],
    tests=check("1 мугалим кошулду", "data.total_added === 1"))
req("Excel: /users/import-excel (сыр сөздөр файлы кайтат)", "POST", "/users/import-excel",
    token="director", files=[("file", "teachers_users.xlsx")])
req("Мугалимдердин убактылуу сыр сөздөрү", "GET", "/admin/teachers/temp-passwords", token="director",
    tests=check("4 мугалим", "data.total === 4")
    + "\n" + save("teacher2_id", "data.teachers.find(t => t.inn === '90000000000011').id")
    + "\n" + save("teacher3_id", "data.teachers.find(t => t.inn === '90000000000012').id")
    + "\n" + check("Сыр сөз тизмеде көрүнөт", "data.teachers.every(t => !!t.temporary_password)"))
req("Сыр сөздөр Excel түрүндө", "GET", "/admin/teachers/temp-passwords?format=xlsx", token="director")
req("Мугалимдин сыр сөзүн reset (/users)", "POST", "/users/{{teacher3_id}}/reset-password", token="director")
req("Мугалимдин сыр сөзүн reset (/admin)", "POST", "/admin/users/{{teacher3_id}}/reset-password", token="director")
req("Колдонуучуну көрүү", "GET", "/users/{{teacher_id}}", token="director")
req("Класс жетекчини дайындоо", "PUT", "/classes/{{class_id}}/class-teacher", token="director",
    body='{"teacher_id": {{teacher_id}}}')
req("Мугалимди сабакка байлоо (ТЗ дареги)", "POST", "/admin/teacher-assignments", token="director",
    body='{"teacher_id": {{teacher_id}}, "class_id": {{class_id}}, "subject_id": {{subject_id}}}',
    expect=201, tests=save("assignment_id", "data.id"))
req("Ошол эле сабакка экинчи мугалим -> 400", "POST", "/admin/teacher-assignments", token="director",
    body='{"teacher_id": {{teacher2_id}}, "class_id": {{class_id}}, "subject_id": {{subject_id}}}',
    expect=400)
req("Мугалимди сабакка байлоо (/teacher-assignments)", "POST", "/teacher-assignments/", token="director",
    body='{"teacher_id": {{teacher2_id}}, "class_id": {{class_id}}, "subject_id": {{subject2_id}}, '
         '"school_id": {{school_id}}, "academic_year": "2026-2027"}',
    tests=save("assignment2_id", "data.id"))
req("Убактылуу бекитүү", "POST", "/teacher-assignments/", token="director",
    body='{"teacher_id": {{teacher3_id}}, "class_id": {{class2_id}}, "subject_id": {{subject_id}}, '
         '"school_id": {{school_id}}, "academic_year": "2026-2027"}',
    tests=save("assignment3_id", "data.id"))
req("Бекитүүлөрдүн тизмеси", "GET", "/teacher-assignments/", token="director",
    tests=check("3 бекитүү", "data.length === 3"))
req("Мугалимдин бекитүүлөрү", "GET", "/teacher-assignments/teacher/{{teacher_id}}", token="director")
req("Бекитүүнү өчүрүү", "DELETE", "/teacher-assignments/{{assignment3_id}}", token="director")
login_flow("Класс жетекчи", "90000000000010", "teacher_pw", "teacher")
login_flow("Экинчи мугалим", "90000000000011", "teacher2_pw", "teacher2")
req("Мугалимдин профили", "GET", "/me", token="teacher", tests=check("Класс жетекчи", "data.is_class_teacher === true"))
req("Мугалим админ эндпоинтине кире албайт -> 403", "GET", "/admin/teachers/temp-passwords", token="teacher", expect=403)

# ============ 5. Окуучулар ============
folder("05. Окуучулар")
req("Excel үлгүсү: окуучулар", "GET", "/admin/excel/templates/students", token="director")
req("Excel: 11-А окуучуларын жүктөө (ТЗ дареги)", "POST", "/admin/excel/import-students",
    token="director", form={"class_id": "{{class_id}}"}, files=[("file", "students_11a.xlsx")],
    tests=check("3 окуучу кошулду", "data.total_added === 3")
    + "\n" + save("erkin_pw", "data.added_students.find(s => s.inn === '90000000000101').temporary_password")
    + "\n" + save("bekzat_pw", "data.added_students.find(s => s.inn === '90000000000102').temporary_password"))
req("Excel: /students/import-excel/{class}", "POST", "/students/import-excel/{{class2_id}}",
    token="director", files=[("file", "students_5b.xlsx")],
    tests=check("1 окуучу кошулду", "data.total_added === 1"))
req("Окуучуну бирден кошуу", "POST", "/students/", token="director",
    body='{"inn": "90000000000105", "full_name": "Жолдошев Адилет", "class_id": {{class2_id}}}',
    tests=save("student5_id", "data.id"))
req("Мугалим окуучу кошо албайт -> 403", "POST", "/students/", token="teacher",
    body='{"inn": "90000000000106", "full_name": "Уруксатсыз Окуучу", "class_id": {{class2_id}}}',
    expect=403)
req("Бардык окуучулар", "GET", "/students/", token="director",
    tests=check("5 окуучу", "data.length === 5"))
req("Класстын окуучулары", "GET", "/students/class/{{class_id}}", token="director",
    tests=check("3 окуучу", "data.length === 3"))
req("Бир окуучу", "GET", "/students/{{student5_id}}", token="director")
req("Окуучуну өзгөртүү", "PUT", "/students/{{student5_id}}", token="director",
    body={"phone": "+996700000105"})
req("Окуучунун тарыхы", "GET", "/students/{{student5_id}}/history", token="director")
req("Окуучуну активсиз кылуу", "DELETE", "/students/{{student5_id}}", token="director")
req("Класс жетекчи: логин жана сыр сөздөр тизмеси", "GET", "/classes/{{class_id}}/temp-passwords",
    token="teacher",
    tests=check("3 окуучу, сыр сөздөрү менен", "data.total === 3 && data.students.every(s => !!s.temporary_password)")
    + "\n" + save("erkin_id", "data.students.find(s => s.inn === '90000000000101').id")
    + "\n" + save("bekzat_id", "data.students.find(s => s.inn === '90000000000102').id")
    + "\n" + save("aidana_id", "data.students.find(s => s.inn === '90000000000103').id"))
req("Сыр сөздөр Excel түрүндө", "GET", "/classes/{{class_id}}/temp-passwords?format=xlsx", token="teacher")
req("Башка мугалим сыр сөздөрдү көрбөйт -> 403", "GET", "/classes/{{class_id}}/temp-passwords",
    token="teacher2", expect=403)
req("Класс жетекчи окуучунун сыр сөзүн reset кылат", "POST",
    "/classes/{{class_id}}/students/{{aidana_id}}/reset-password", token="teacher")

# ============ 6. Ата-эне жана окуучу ============
folder("06. Ата-эне жана окуучунун аккаунттары")
req("Ата-эне катталат (баласынын ИНН + убактылуу сыр сөзү)", "POST", "/parents/register",
    body='{"inn": "90000000000201", "full_name": "Асанова Назира", "password": "Parent#2026", '
         '"student_inn": "90000000000101", "student_password": "{{erkin_pw}}"}',
    tests=save("parent", "data.access_token"))
req("Экинчи баласын кошуу", "POST", "/parents/add-child", token="parent",
    body='{"student_inn": "90000000000102", "student_password": "{{bekzat_pw}}"}')
req("Менин балдарым", "GET", "/parents/my-children", token="parent",
    tests=check("2 бала", "data.total_children === 2"))
req("Ата-эненин профили", "GET", "/me", token="parent",
    tests=check("Балдары класс аты менен", "data.children.length === 2 && data.children[0].class_name === '11-А'"))
login_flow("Окуучу", "90000000000101", "erkin_pw", "student")
req("Окуучунун профили", "GET", "/me", token="student",
    tests=check("Классы 11-А", "data.student.class_name === '11-А'"))

# ============ 7. Журнал ============
folder("07. Электрондук журнал")
req("Мугалимдин журналдары", "GET", "/journal/assignments", token="teacher",
    tests=check("Өз сабагын оңдой алат", "data.some(a => a.can_edit)"))
JOURNAL = ('{"assignment_id": {{assignment_id}}, "date": "{{today}}", "entries": ['
           '{"student_id": {{erkin_id}}, "grade_value": 5, "attendance": "Б"}, '
           '{"student_id": {{bekzat_id}}, "grade_value": 4, "attendance": "Б"}, '
           '{"student_id": {{aidana_id}}, "grade_value": 3, "attendance": "К", "comment": "Кечикти"}]}')
req("Директор баа коё албайт -> 403", "PUT", "/journal", token="director", body=JOURNAL, expect=403)
req("Башка мугалим бөтөн сабакка баа коё албайт -> 403", "PUT", "/journal", token="teacher2",
    body=JOURNAL, expect=403)
req("Окуучу баа коё албайт -> 403", "PUT", "/journal", token="student", body=JOURNAL, expect=403)
req("Мугалим баа жана катышуу коёт", "PUT", "/journal", token="teacher", body=JOURNAL,
    tests=check("3 жазуу сакталды", "data.saved === 3"))
req("«С» белгисин кол менен коюуга болбойт -> 400", "PUT", "/journal", token="teacher",
    body='{"assignment_id": {{assignment_id}}, "date": "{{today}}", "entries": ['
         '{"student_id": {{aidana_id}}, "attendance": "С"}]}', expect=400)
req("Келечектеги күнгө баа -> 400", "PUT", "/journal", token="teacher",
    body='{"assignment_id": {{assignment_id}}, "date": "{{day2}}", "entries": ['
         '{"student_id": {{aidana_id}}, "grade_value": 5}]}', expect=400)
req("Журналды көрүү", "GET", "/journal?assignment_id={{assignment_id}}&day={{today}}", token="teacher",
    tests=check("Эркинге 5 коюлган", "data.students.find(s => s.student_id == pm.collectionVariables.get('erkin_id')).grade_value === 5"))
req("Директор журналды көрөт (көрүү гана)", "GET",
    "/journal?assignment_id={{assignment_id}}&day={{today}}", token="director",
    tests=check("can_edit = false", "data.can_edit === false"))
req("Экинчи мугалим өз сабагына баа коёт", "PUT", "/journal", token="teacher2",
    body='{"assignment_id": {{assignment2_id}}, "date": "{{today}}", "entries": ['
         '{"student_id": {{aidana_id}}, "grade_value": 5, "attendance": "Б"}, '
         '{"student_id": {{bekzat_id}}, "grade_value": 2, "attendance": "Б"}]}')
req("Экинчи сабактын журналы", "GET", "/journal?assignment_id={{assignment2_id}}&day={{today}}",
    token="teacher2",
    tests=save("entry_id", "data.students.find(s => s.student_id == pm.collectionVariables.get('bekzat_id')).entry_id"))
req("Жазууну өчүрүү", "DELETE", "/journal/entries/{{entry_id}}", token="teacher2")
req("Класс жетекчи: класстын бир күнкү сабактары", "GET", "/journal/class/{{class_id}}?day={{today}}",
    token="teacher", tests=check("3 окуучу", "data.students.length === 3"))
req("Окуучунун күндөлүгү", "GET", "/journal/diary", token="student",
    tests=check("Бүгүнкү баасы көрүнөт", "data.days[0].lessons[0].grade_value === 5"))
req("Окуучу башканын күндөлүгүн көрбөйт -> 403", "GET", "/journal/diary?student_id={{bekzat_id}}",
    token="student", expect=403)
req("Ата-эне: баласынын күндөлүгү", "GET", "/journal/diary?student_id={{bekzat_id}}", token="parent")
req("Ата-эне: предметтер боюнча жыйынтык", "GET", "/journal/summary?student_id={{erkin_id}}",
    token="parent", tests=check("Орточо баа 5", "data.overall_average === 5"))

# ============ 8. Сабактан сурануу ============
folder("08. Сабактан сурануу (ата-эне гана, 08:00 эрежеси)")
req("Сурануу баскычынын абалы", "GET", "/absence-requests/status", token="parent",
    tests=check("Ата-эне жөнөтө алат", "data.can_submit === true")
    + "\n" + save("open_today", "data.is_open_for_today ? '1' : ''"))
req("ОКУУЧУ сурануу жибере албайт -> 403", "POST", "/absence-requests", token="student",
    body='{"reason": "Оору", "target_date": "{{tomorrow}}"}', expect=403)
req("ОКУУЧУ суранууларды көрө албайт -> 403", "GET", "/absence-requests", token="student", expect=403)
req("ОКУУЧУ баскычтын абалын көрбөйт -> 403", "GET", "/absence-requests/status", token="student", expect=403)
req("Мугалим сурануу жибере албайт -> 403", "POST", "/absence-requests", token="teacher",
    body='{"student_id": {{erkin_id}}, "reason": "Оору", "target_date": "{{tomorrow}}"}', expect=403)
req("Директор сурануу жибере албайт -> 403", "POST", "/absence-requests", token="director",
    body='{"student_id": {{erkin_id}}, "reason": "Оору", "target_date": "{{tomorrow}}"}', expect=403)
req("Ата-эне бөтөн балага сурана албайт -> 403", "POST", "/absence-requests", token="parent",
    body='{"student_id": {{aidana_id}}, "reason": "Оору", "target_date": "{{tomorrow}}"}', expect=403)
req("Ата-эне: БҮГҮНКҮ күнгө (08:00гө чейин 201, кийин 403)", "POST", "/absence-requests",
    token="parent", body='{"student_id": {{bekzat_id}}, "reason": "Оору"}',
    expect="pm.collectionVariables.get('open_today') ? 201 : 403")
req("Ата-эне: өткөн күнгө -> 400", "POST", "/absence-requests", token="parent",
    body='{"student_id": {{erkin_id}}, "reason": "Оору", "target_date": "{{yesterday}}"}', expect=400)
req("Ата-эне: эртеңки күнгө сурануу", "POST", "/absence-requests", token="parent",
    body='{"student_id": {{erkin_id}}, "reason": "Оору", "comment": "Температурасы бар", "target_date": "{{tomorrow}}"}',
    expect=201, tests=save("req1", "data.id") + "\n" + check("Статусу PENDING", "data.status === 'PENDING'"))
req("Ошол эле күнгө кайра -> 409", "POST", "/absence-requests", token="parent",
    body='{"student_id": {{erkin_id}}, "reason": "Оору", "target_date": "{{tomorrow}}"}', expect=409)
req("Ата-эне: 2 күндөн кийинкиге", "POST", "/absence-requests", token="parent",
    body='{"student_id": {{erkin_id}}, "reason": "Үй-бүлөлүк шарт", "target_date": "{{day2}}"}',
    expect=201, tests=save("req2", "data.id"))
req("Ата-эне: 3 күндөн кийинкиге", "POST", "/absence-requests", token="parent",
    body='{"student_id": {{erkin_id}}, "reason": "Дарыгерге баруу", "target_date": "{{day3}}"}',
    expect=201, tests=save("req3", "data.id"))
req("Ата-эненин суранычтары", "GET", "/absence-requests", token="parent",
    tests=check("Кеминде 3", "data.length >= 3"))
req("Класс жетекчи: каралбаган суранычтар", "GET", "/absence-requests?status=PENDING", token="teacher",
    tests=check("Кеминде 3", "data.length >= 3"))
req("Класс жетекчи эмес мугалим көрбөйт -> 403", "GET", "/absence-requests", token="teacher2", expect=403)
req("Директор көзөмөлдөйт", "GET", "/absence-requests", token="director")
req("Бир сурануу", "GET", "/absence-requests/{{req1}}", token="parent")
req("Директор беките албайт -> 403", "POST", "/absence-requests/{{req1}}/approve", token="director", expect=403)
req("Ата-эне өзү беките албайт -> 403", "POST", "/absence-requests/{{req1}}/approve", token="parent", expect=403)
req("Класс жетекчи уруксат берет", "POST", "/absence-requests/{{req1}}/approve", token="teacher",
    tests=check("Статусу APPROVED", "data.status === 'APPROVED'"))
req("Экинчи жолу бекитүү -> 400", "POST", "/absence-requests/{{req1}}/approve", token="teacher", expect=400)
req("Класс жетекчи четке кагат", "POST", "/absence-requests/{{req2}}/reject", token="teacher",
    body={"comment": "Документ жок"}, tests=check("Статусу REJECTED", "data.status === 'REJECTED'"))
req("Ата-эне суранычын жокко чыгарат", "POST", "/absence-requests/{{req3}}/cancel", token="parent",
    tests=check("Статусу CANCELLED", "data.status === 'CANCELLED'"))

# ============ 9. Үй тапшырма ============
folder("09. Үй тапшырма")
req("Бөтөн мугалим тапшырма түзө албайт -> 403", "POST", "/homeworks", token="teacher2",
    form={"assignment_id": "{{assignment_id}}", "title": "Уруксатсыз"}, expect=403)
req("Мугалим үй тапшырма түзөт (сүрөт + PDF)", "POST", "/homeworks", token="teacher",
    form={"assignment_id": "{{assignment_id}}", "title": "№234, 235, 236 көнүгүүлөр",
          "description": "Китептин 45-бети", "due_date": "{{tomorrow}}"},
    files=[("files", "page.png"), ("files", "formula.pdf")], expect=201,
    tests=save("hw_id", "data.id") + "\n" + save("hw_image", "data.image_urls[0].slice(1)")
    + "\n" + check("1 сүрөт + 1 файл", "data.image_urls.length === 1 && data.file_urls.length === 1"))
req("Сүрөт статикалык дарек менен ачылат", "GET", "/{{hw_image}}")
req("Окуучу: тапшырмалар", "GET", "/homeworks", token="student",
    tests=check("1 тапшырма, тапшырыла элек", "data.length === 1 && data[0].is_submitted === false"))
req("Ата-эне: баласынын тапшырмалары", "GET", "/homeworks?student_id={{bekzat_id}}", token="parent",
    tests=check("1 тапшырма", "data.length === 1"))
req("Бир тапшырма", "GET", "/homeworks/{{hw_id}}", token="student")
req("Тапшырманы өзгөртүү", "PUT", "/homeworks/{{hw_id}}", token="teacher",
    form={"title": "№234-236 көнүгүүлөр (жаңыртылды)"})
req("Кошумча файл тиркөө", "POST", "/homeworks/{{hw_id}}/files", token="teacher",
    files=[("files", "extra.png")],
    tests=check("2 сүрөт", "data.image_urls.length === 2") + "\n" + save("hw_extra", "data.image_urls[1]"))
req("Файлды алып салуу", "DELETE", "/homeworks/{{hw_id}}/files?url={{hw_extra}}", token="teacher",
    tests=check("1 сүрөт калды", "data.image_urls.length === 1"))
req("Окуучу тапшырманы тапшырат", "POST", "/homeworks/{{hw_id}}/submit", token="student",
    form={"text": "Аткардым"}, files=[("files", "extra.png")])
req("Ата-эне тапшыра албайт -> 403", "POST", "/homeworks/{{hw_id}}/submit", token="parent",
    form={"text": "Мен аткардым"}, expect=403)
req("Мугалим: тапшырылган иштер", "GET", "/homeworks/{{hw_id}}/submissions", token="teacher",
    tests=check("1 иш", "data.length === 1"))

# ============ 10. Рейтинг ============
folder("10. Рейтинг жана значоктор")
req("Класс ичиндеги рейтинг", "GET", "/ratings/class/{{class_id}}", token="student",
    tests=check("3 окуучу, 1-орун бар", "data.items.length === 3 && data.items[0].rank === 1"))
req("Параллель рейтинги (11-класстар)", "GET", "/ratings/parallel/11", token="student")
req("Мектеп боюнча жалпы рейтинг", "GET", "/ratings/school", token="parent")
req("Предметтик рейтинг", "GET", "/ratings/subjects/{{subject_id}}", token="student")
req("Предмет боюнча Топ (мугалим)", "GET", "/ratings/subjects/{{subject_id}}/top", token="teacher",
    tests=check("Топто окуучулар бар", "data.items.length >= 1 && data.items.length <= 3"))
req("Топту окуучу көрбөйт -> 403", "GET", "/ratings/subjects/{{subject_id}}/top", token="student", expect=403)
req("Менин ордум", "GET", "/ratings/me", token="student",
    tests=check("XP = 55 (5 -> +50, Б -> +5)", "data.total_xp === 55")
    + "\n" + check("Значоктору бар", "data.badges.length >= 1"))
req("Окуучунун профили (значоктору менен)", "GET", "/profiles/students/{{erkin_id}}", token="teacher")
req("Ата-эне бөтөн баланын профилин көрбөйт -> 403", "GET", "/profiles/students/{{aidana_id}}",
    token="parent", expect=403)
req("Рейтингди кайра эсептөө", "POST", "/ratings/recompute", token="director")

# ============ 11. Олимпиада ============
folder("11. Олимпиадалык аналитика")
req("Аналитика: предметтер боюнча Топ-3", "GET", "/olympiad/analytics", token="director",
    tests=check("2 предмет", "data.subjects.length === 2"))
req("Мугалим талапкер сунуштайт", "POST", "/olympiad/candidates", token="teacher",
    body='{"subject_id": {{subject_id}}, "student_id": {{aidana_id}}, "note": "Жөндөмдүү"}',
    expect=201, tests=save("cand_id", "data.id") + "\n" + check("SUGGESTED", "data.status === 'SUGGESTED'"))
req("Мугалим беките албайт -> 403", "POST", "/olympiad/candidates/{{cand_id}}/approve",
    token="teacher", expect=403)
req("Завуч/директор сунушту бекитет", "POST", "/olympiad/candidates/{{cand_id}}/approve",
    token="director", tests=check("SELECTED", "data.status === 'SELECTED'"))
req("Топ-3тү автоматтык тандоо", "POST", "/olympiad/auto-select", token="director",
    body='{"subject_id": {{subject_id}}}')
req("Талапкерлердин тизмеси", "GET", "/olympiad/candidates?status=SELECTED", token="director",
    tests=check("Талапкерлер бар", "data.length >= 1"))
req("Талапкерди тизмеден алуу", "DELETE", "/olympiad/candidates/{{cand_id}}", token="director")

# ============ 12. Жарыялар жана билдирүүлөр ============
folder("12. Жарыялар, билдирүүлөр, башкы панель")
req("Мугалим жарыя түзө албайт -> 403", "POST", "/announcements", token="teacher",
    form={"title": "Уруксатсыз жарыя"}, expect=403)
req("Жарыя түзүү (сүрөт менен)", "POST", "/announcements", token="director",
    form={"title": "Республикалык олимпиада", "body": "27-апрелде Кыргыз тили боюнча олимпиада өтөт",
          "event_date": "{{day3}}"},
    files=[("image", "page.png")], expect=201, tests=save("ann_id", "data.id"))
req("Жарыялар", "GET", "/announcements", token="student",
    tests=check("1 жарыя", "data.length === 1"))
req("Бир жарыя", "GET", "/announcements/{{ann_id}}", token="parent")
req("Жарыяны өзгөртүү", "PUT", "/announcements/{{ann_id}}", token="director",
    form={"title": "Республикалык олимпиада (жаңыртылды)"})
req("Билдирүүлөр (класс жетекчи)", "GET", "/notifications", token="teacher",
    tests=check("Сурануу жөнүндө билдирүү келген", "data.some(n => n.title === 'Жаңы сурануу')")
    + "\n" + save("notif_id", "data[0].id"))
req("Окулбаган билдирүүлөрдүн саны", "GET", "/notifications/unread-count", token="teacher",
    tests=check("Окулбагандар бар", "data.unread >= 1"))
req("Бир билдирүүнү окулду кылуу", "POST", "/notifications/{{notif_id}}/read", token="teacher")
req("Баарын окулду кылуу", "POST", "/notifications/read-all", token="teacher")
req("Ата-энеге чечим жөнүндө билдирүү келген", "GET", "/notifications", token="parent",
    tests=check("Кабыл алынды + четке кагылды",
                "data.some(n => n.title === 'Сурануу кабыл алынды') && data.some(n => n.title === 'Сурануу четке кагылды')"))
req("Башкы панелдин статистикасы", "GET", "/dashboard/stats", token="student",
    tests=check("4 окуучу, 4 мугалим, 2 класс", "data.students === 4 && data.teachers === 4 && data.classes === 2"))
req("Аватар жүктөө", "POST", "/me/avatar", token="student", files=[("file", "page.png")])
req("Сыр сөздү алмаштыруу", "POST", "/me/change-password", token="student",
    body={"current_password": NEW_PW, "new_password": "Another#2026"})
req("Жаңы сыр сөз менен кирүү", "POST", "/auth/login",
    body={"inn": "90000000000101", "password": "Another#2026"},
    tests=check("Убактылуу эмес", "data.requires_password_change === false"))

# ============ 13. Multi-tenant ============
folder("13. Мектептердин изоляциясы (multi-tenant)")
req("Башка мектеп классты көрбөйт -> 404", "GET", "/classes/{{class_id}}", token="other_director", expect=404)
req("Башка мектеп үй тапшырманы көрбөйт -> 404", "GET", "/homeworks/{{hw_id}}", token="other_director", expect=404)
req("Башка мектеп суранууну көрбөйт -> 404", "GET", "/absence-requests/{{req1}}", token="other_director", expect=404)
req("Башка мектеп сыр сөздөрдү көрбөйт -> 404", "GET", "/classes/{{class_id}}/temp-passwords",
    token="other_director", expect=404)
req("Башка мектептин жарыялары бош", "GET", "/announcements", token="other_director",
    tests=check("Бош тизме", "data.length === 0"))
req("Башка мектептин окуучулары бош", "GET", "/students/", token="other_director",
    tests=check("Бош тизме", "data.length === 0"))

# ============ 14. Аяктоо ============
folder("14. Тазалоо жана кийинки окуу жылына өткөрүү")
req("Жарыяны өчүрүү", "DELETE", "/announcements/{{ann_id}}", token="director")
req("Үй тапшырманы өчүрүү", "DELETE", "/homeworks/{{hw_id}}", token="teacher")
req("Өткөрүүнү алдын ала көрүү", "GET",
    "/students/promotion/preview?source_academic_year=2026-2027&target_academic_year=2027-2028",
    token="director")
req("Окуучуларды кийинки жылга өткөрүү", "POST", "/students/promotion/execute", token="director",
    body={"source_academic_year": "2026-2027", "target_academic_year": "2027-2028", "excluded_student_ids": []})
req("Кайра өткөрүү четке кагылат -> 404", "POST", "/students/promotion/execute", token="director",
    body={"source_academic_year": "2026-2027", "target_academic_year": "2027-2028", "excluded_student_ids": []},
    expect=404)

# ---------- коллекция деңгээлиндеги скрипт: Бишкек убактысы боюнча даталар ----------
PREREQUEST = """
const bishkek = offset => new Date(Date.now() + 6 * 3600 * 1000 + offset * 86400 * 1000)
    .toISOString().slice(0, 10);
pm.collectionVariables.set('yesterday', bishkek(-1));
pm.collectionVariables.set('today', bishkek(0));
pm.collectionVariables.set('tomorrow', bishkek(1));
pm.collectionVariables.set('day2', bishkek(2));
pm.collectionVariables.set('day3', bishkek(3));
""".strip().splitlines()

collection = {
    "info": {
        "name": "Smart School API",
        "description": (
            "Smart School бэкендинин бардык эндпоинттери. Папкаларды жогортон төмөн "
            "иретинде иштетиңиз (Run collection). Таза тест базасын талап кылат: "
            "`python postman/seed_test_db.py`."
        ),
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
    },
    "variable": [
        {"key": "base_url", "value": "http://127.0.0.1:8010"},
        {"key": "director_pw", "value": "Mektep#2026"},
    ],
    "event": [{"listen": "prerequest", "script": {"type": "text/javascript", "exec": PREREQUEST}}],
    "item": folders,
}

out = ROOT / "SmartSchool.postman_collection.json"
out.write_text(json.dumps(collection, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"{counter} суроо -> {out}")

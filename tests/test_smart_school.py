"""Smart School бэкендинин башынан аягына чейинки сценарийи (ТЗ v2.0 боюнча)."""
from datetime import timedelta
from io import BytesIO

import pytest
from openpyxl import Workbook

from mysite.db.models import Schools, Users
from mysite.security.hashing import hash_password

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
S = {}  # тесттер ортосунда бөлүшүлгөн абал


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def login(client, email, password):
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def login_and_change(client, email, temp_password, new_password="NewPass#2026"):
    data = login(client, email, temp_password)
    assert data["requires_password_change"] is True
    r = client.post(
        "/auth/first-login-change",
        headers=auth(data["access_token"]),
        json={"current_password": temp_password, "new_password": new_password},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def excel(rows):
    wb = Workbook()
    ws = wb.active
    ws.append(["Почта", "Толук аты-жөнү"])
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# =====================================================
# 1. Мектеп, завуч, класс, мугалимдер, Excel
# =====================================================

def test_setup_school(client, db):
    for key, name in (("school", "Тест мектеп №1"), ("other_school", "Тест мектеп №2")):
        school = Schools(name=name)
        db.add(school)
        db.flush()
        S[key] = school.id

    db.add(Users(email="u90000000000001@test.kg", full_name="Тест Директор", role="DIRECTOR",
                 hashed_password=hash_password("Mektep#2026"), school_id=S["school"]))
    db.add(Users(email="u90000000000002@test.kg", full_name="Башка Директор", role="DIRECTOR",
                 hashed_password=hash_password("Mektep#2026"), school_id=S["other_school"],
                 is_temp_password=False))
    db.commit()

    S["director"] = login_and_change(client, "u90000000000001@test.kg", "Mektep#2026")
    S["other_director"] = login(client, "u90000000000002@test.kg", "Mektep#2026")["access_token"]


def test_class_subject_teachers(client):
    h = auth(S["director"])

    r = client.post("/classes/", headers=h, json={
        "grade_number": 11, "letter": "А", "academic_year": "2026-2027"})
    assert r.status_code == 200, r.text
    S["class"] = r.json()["id"]

    r = client.post("/subjects/", headers=h, json={"name": "Кыргыз тили"})
    assert r.status_code == 200, r.text
    S["subject"] = r.json()["id"]

    # Мугалимдерди Excel менен жүктөө (ТЗдагы дарек)
    r = client.post("/admin/excel/import-teachers", headers=h, files={
        "file": ("teachers.xlsx", excel([
            ["u90000000000010@test.kg", "Класс Жетекчи Мугалим"],
            ["u90000000000011@test.kg", "Башка Мугалим"],
            ["123", "Ката почта"],
        ]), XLSX)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_added"] == 2 and body["total_errors"] == 1
    teacher_pw = {t["email"]: t["temporary_password"] for t in body["added_teachers"]}

    # Завуч мугалимдердин убактылуу сыр сөздөрүн кийин да ала алат
    r = client.get("/admin/teachers/temp-passwords", headers=h)
    listed = {t["email"]: t for t in r.json()["teachers"]}
    assert listed["u90000000000010@test.kg"]["temporary_password"] == teacher_pw["u90000000000010@test.kg"]
    S["teacher_id"] = listed["u90000000000010@test.kg"]["id"]
    S["teacher2_id"] = listed["u90000000000011@test.kg"]["id"]

    r = client.put(f"/classes/{S['class']}/class-teacher", headers=h,
                   json={"teacher_id": S["teacher_id"]})
    assert r.status_code == 200, r.text

    r = client.post("/admin/teacher-assignments", headers=h, json={
        "teacher_id": S["teacher_id"], "class_id": S["class"], "subject_id": S["subject"]})
    assert r.status_code == 201, r.text
    S["assignment"] = r.json()["id"]

    # Ошол эле класс+предметке экинчи мугалим бекитилбейт
    r = client.post("/admin/teacher-assignments", headers=h, json={
        "teacher_id": S["teacher2_id"], "class_id": S["class"], "subject_id": S["subject"]})
    assert r.status_code == 400

    S["teacher"] = login_and_change(client, "u90000000000010@test.kg", teacher_pw["u90000000000010@test.kg"])
    S["teacher2"] = login_and_change(client, "u90000000000011@test.kg", teacher_pw["u90000000000011@test.kg"])

    # Сыр сөз алмашкандан кийин убактылуу сыр сөз базадан өчөт
    r = client.get("/admin/teachers/temp-passwords", headers=h)
    listed = {t["email"]: t for t in r.json()["teachers"]}
    assert listed["u90000000000010@test.kg"]["temporary_password"] is None


def test_import_students_and_temp_passwords(client):
    h = auth(S["director"])

    r = client.get("/admin/excel/templates/students", headers=h)
    assert r.status_code == 200 and r.content[:2] == b"PK"

    r = client.post("/admin/excel/import-students", headers=h,
                    data={"class_id": str(S["class"])},
                    files={"file": ("students.xlsx", excel([
                        ["u90000000000101@test.kg", "Алиев Эркин"],
                        ["u90000000000102@test.kg", "Токтосунов Бекзат"],
                        ["u90000000000103@test.kg", "Жумабекова Айдана"],
                    ]), XLSX)})
    assert r.status_code == 200, r.text
    assert r.json()["total_added"] == 3

    # Класс жетекчи өз классынын логин/сыр сөздөрүн алат
    r = client.get(f"/classes/{S['class']}/temp-passwords", headers=auth(S["teacher"]))
    assert r.status_code == 200, r.text
    students = r.json()["students"]
    assert len(students) == 3 and all(s["temporary_password"] for s in students)
    S["students"] = {s["email"]: s for s in students}

    r = client.get(f"/classes/{S['class']}/temp-passwords?format=xlsx", headers=auth(S["teacher"]))
    assert r.status_code == 200 and r.content[:2] == b"PK"

    # Башка мугалим көрө албайт
    r = client.get(f"/classes/{S['class']}/temp-passwords", headers=auth(S["teacher2"]))
    assert r.status_code == 403

    # Башка мектептин директору бул классты таптакыр көрбөйт (multi-tenant)
    r = client.get(f"/classes/{S['class']}/temp-passwords", headers=auth(S["other_director"]))
    assert r.status_code == 404


def test_parent_and_student_accounts(client):
    erkin = S["students"]["u90000000000101@test.kg"]
    bekzat = S["students"]["u90000000000102@test.kg"]

    r = client.post("/parents/register", json={
        "email": "u90000000000201@test.kg", "full_name": "Асанова Назира", "password": "Parent#2026",
        "student_code": erkin["parent_code"]})
    assert r.status_code == 200, r.text
    S["parent"] = r.json()["access_token"]

    r = client.post("/parents/add-child", headers=auth(S["parent"]), json={
        "student_code": bekzat["parent_code"]})
    assert r.status_code == 200, r.text

    S["erkin_id"], S["bekzat_id"] = erkin["id"], bekzat["id"]
    S["aidana_id"] = S["students"]["u90000000000103@test.kg"]["id"]
    S["erkin"] = login_and_change(client, erkin["email"], erkin["temporary_password"])

    r = client.get("/me", headers=auth(S["parent"]))
    assert r.status_code == 200 and len(r.json()["children"]) == 2
    assert r.json()["children"][0]["class_name"] == "11-А"

    # Ошол эле баланы кайра кошууга болбойт
    r = client.post("/parents/add-child", headers=auth(S["parent"]), json={
        "student_code": bekzat["parent_code"]})
    assert r.status_code == 400

    # Экинчи ата-эне (ата) ошол эле балага байланат, үчүнчүсү — жок
    r = client.post("/parents/register", json={
        "email": "u90000000000202@test.kg", "full_name": "Асанов Бакыт", "password": "Parent#2026",
        "student_code": bekzat["parent_code"]})
    assert r.status_code == 200, r.text
    second_parent = r.json()["access_token"]
    r = client.get(f"/journal/summary?student_id={bekzat['id']}", headers=auth(second_parent))
    assert r.status_code == 200

    r = client.post("/parents/register", json={
        "email": "u90000000000203@test.kg", "full_name": "Үчүнчү Ата-эне", "password": "Parent#2026",
        "student_code": bekzat["parent_code"]})
    assert r.status_code == 400


# =====================================================
# 2. Сабактан сурануу: АТА-ЭНЕ ГАНА, 08:00 эрежеси
# =====================================================

def test_student_cannot_request_absence(client, freeze_time):
    freeze_time(7, 30)
    h = auth(S["erkin"])

    r = client.post("/absence-requests", headers=h, json={"reason": "Оору"})
    assert r.status_code == 403

    assert client.get("/absence-requests", headers=h).status_code == 403
    assert client.get("/absence-requests/status", headers=h).status_code == 403


def test_non_parents_cannot_request_absence(client, freeze_time):
    freeze_time(7, 30)
    for token in (S["teacher"], S["director"]):
        r = client.post("/absence-requests", headers=auth(token),
                        json={"student_id": S["erkin_id"], "reason": "Оору"})
        assert r.status_code == 403


def test_parent_request_before_8(client, freeze_time):
    freeze_time(7, 59, 59)
    h = auth(S["parent"])

    r = client.get("/absence-requests/status", headers=h)
    assert r.json()["is_open_for_today"] is True and r.json()["can_submit"] is True

    # Эки баласы бар — student_id милдеттүү
    r = client.post("/absence-requests", headers=h, json={"reason": "Оору"})
    assert r.status_code == 400

    # Бөтөн бала үчүн сурана албайт
    r = client.post("/absence-requests", headers=h,
                    json={"student_id": S["aidana_id"], "reason": "Оору"})
    assert r.status_code == 403

    r = client.post("/absence-requests", headers=h, json={
        "student_id": S["erkin_id"], "reason": "Оору", "comment": "Температурасы бар"})
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "PENDING"
    S["request"] = r.json()["id"]

    # Ошол эле күнгө экинчи сурануу болбойт
    r = client.post("/absence-requests", headers=h,
                    json={"student_id": S["erkin_id"], "reason": "Оору"})
    assert r.status_code == 409


def test_parent_request_locked_at_8(client, freeze_time):
    frozen = freeze_time(8, 0, 0)
    h = auth(S["parent"])

    r = client.get("/absence-requests/status", headers=h)
    assert r.json()["is_open_for_today"] is False

    r = client.post("/absence-requests", headers=h,
                    json={"student_id": S["bekzat_id"], "reason": "Оору"})
    assert r.status_code == 403
    assert "08:00" in r.json()["detail"]

    # Өткөн күнгө болбойт
    r = client.post("/absence-requests", headers=h, json={
        "student_id": S["bekzat_id"], "reason": "Оору",
        "target_date": str(frozen.date() - timedelta(days=1))})
    assert r.status_code == 400

    # Эртеңки күнгө алдын ала суранса болот
    r = client.post("/absence-requests", headers=h, json={
        "student_id": S["bekzat_id"], "reason": "Үй-бүлөлүк шарт",
        "target_date": str(frozen.date() + timedelta(days=1))})
    assert r.status_code == 201, r.text
    S["request_tomorrow"] = r.json()["id"]


# =====================================================
# 3. Журнал, XP жана суранууну бекитүү («С»)
# =====================================================

def test_journal_rbac_and_xp(client, freeze_time):
    frozen = freeze_time(10, 0)
    today = str(frozen.date())
    payload = {"assignment_id": S["assignment"], "date": today, "entries": [
        {"student_id": S["erkin_id"], "grade_value": 5, "attendance": "Б"},
        {"student_id": S["bekzat_id"], "grade_value": 4, "attendance": "Б"},
        {"student_id": S["aidana_id"], "grade_value": 2, "attendance": "К"},
    ]}

    # Башка мугалим, директор, окуучу баа коё албайт
    for token in (S["teacher2"], S["director"], S["erkin"], S["parent"]):
        assert client.put("/journal", headers=auth(token), json=payload).status_code == 403

    r = client.put("/journal", headers=auth(S["teacher"]), json=payload)
    assert r.status_code == 200, r.text

    # «С» белгисин мугалим кол менен коё албайт
    r = client.put("/journal", headers=auth(S["teacher"]), json={
        "assignment_id": S["assignment"], "date": today,
        "entries": [{"student_id": S["aidana_id"], "attendance": "С"}]})
    assert r.status_code == 400

    r = client.get(f"/ratings/class/{S['class']}", headers=auth(S["erkin"]))
    items = {i["student_id"]: i for i in r.json()["items"]}
    assert items[S["erkin_id"]]["xp"] == 55 and items[S["erkin_id"]]["rank"] == 1
    assert items[S["bekzat_id"]]["xp"] == 35
    assert items[S["aidana_id"]]["xp"] == -20

    # Директор журналды көрөт (көрүү гана)
    r = client.get(f"/journal?assignment_id={S['assignment']}&day={today}", headers=auth(S["director"]))
    assert r.status_code == 200 and r.json()["can_edit"] is False

    # Окуучунун күндөлүгү; башка окуучунукун көрө албайт
    r = client.get("/journal/diary", headers=auth(S["erkin"]))
    assert r.json()["days"][0]["lessons"][0]["grade_value"] == 5
    r = client.get(f"/journal/diary?student_id={S['bekzat_id']}", headers=auth(S["erkin"]))
    assert r.status_code == 403
    r = client.get(f"/journal/summary?student_id={S['bekzat_id']}", headers=auth(S["parent"]))
    assert r.status_code == 200 and r.json()["overall_average"] == 4


def test_journal_month_periods_and_performance(client, freeze_time):
    frozen = freeze_time(10, 0)
    today = str(frozen.date())
    month = today[:7]

    # Айлык табель: директор көрөт, бирок баа коё албайт; окуучуга жабык
    r = client.get(f"/journal/month?assignment_id={S['assignment']}&month={month}", headers=auth(S["director"]))
    assert r.status_code == 200, r.text
    assert r.json()["can_edit"] is False
    erkin = next(row for row in r.json()["students"] if row["student_id"] == S["erkin_id"])
    assert any(c["date"] == today and c["grade_value"] == 5 for c in erkin["cells"])
    assert erkin["average"] == 5
    r = client.get(f"/journal/month?assignment_id={S['assignment']}&month=2026-13", headers=auth(S["teacher"]))
    assert r.status_code == 400
    r = client.get(f"/journal/month?assignment_id={S['assignment']}", headers=auth(S["erkin"]))
    assert r.status_code == 403

    # Чейрек: орточо баа эсептелет, жыйынтык бааны сабактын мугалими гана коёт
    r = client.get(f"/journal/periods?assignment_id={S['assignment']}", headers=auth(S["teacher"]))
    assert r.status_code == 200, r.text
    current = r.json()["current_period"]
    assert current is not None
    erkin = next(row for row in r.json()["students"] if row["student_id"] == S["erkin_id"])
    assert erkin["grades"][current]["average"] == 5

    payload = {"assignment_id": S["assignment"], "period": current,
               "entries": [{"student_id": S["erkin_id"], "grade_value": 5}]}
    for token in (S["teacher2"], S["director"], S["erkin"]):
        assert client.put("/journal/periods", headers=auth(token), json=payload).status_code == 403
    r = client.put("/journal/periods", headers=auth(S["teacher"]), json=payload)
    assert r.status_code == 200 and r.json()["saved"] == 1, r.text

    r = client.get(f"/journal/periods?assignment_id={S['assignment']}", headers=auth(S["teacher"]))
    erkin = next(row for row in r.json()["students"] if row["student_id"] == S["erkin_id"])
    assert erkin["grades"][current]["final"] == 5 and erkin["grades"]["YEAR"]["average"] == 5

    r = client.get("/journal/summary", headers=auth(S["erkin"]))
    assert any(subject["period_grades"].get(current) == 5 for subject in r.json()["subjects"])

    payload["entries"][0]["grade_value"] = None
    r = client.put("/journal/periods", headers=auth(S["teacher"]), json=payload)
    assert r.status_code == 200 and r.json()["deleted"] == 1

    # Окуучунун айлык табели: өзү жана ата-энеси көрөт, башка окуучу көрө албайт
    r = client.get(f"/journal/my-month?month={month}", headers=auth(S["erkin"]))
    assert r.status_code == 200, r.text
    assert any(
        cell["date"] == today and cell["grade_value"] == 5
        for row in r.json()["rows"] for cell in row["cells"]
    )
    r = client.get(f"/journal/my-month?student_id={S['bekzat_id']}&month={month}", headers=auth(S["parent"]))
    assert r.status_code == 200, r.text
    r = client.get(f"/journal/my-month?student_id={S['bekzat_id']}", headers=auth(S["erkin"]))
    assert r.status_code == 403

    # Башкы панелдин графиги: бүгүн 5, 4, 2 → орточо 3.67 → 73%, катышуу 100%
    r = client.get("/dashboard/performance?period=week", headers=auth(S["director"]))
    assert r.status_code == 200, r.text
    points = r.json()["points"]
    assert len(points) == 7 and points[-1]["date"] == today
    assert points[-1]["percent"] == 73 and points[-1]["attendance_percent"] == 100
    r = client.get("/dashboard/performance?period=year", headers=auth(S["director"]))
    assert len(r.json()["points"]) == 12
    assert client.get("/dashboard/performance", headers=auth(S["teacher"])).status_code == 403


def test_announcement_audience(client):
    r = client.post("/announcements", headers=auth(S["director"]),
                    data={"title": "Ата-энелер чогулушу", "audience": "PARENT,STUDENT"})
    assert r.status_code == 201, r.text
    assert r.json()["audience"] == ["STUDENT", "PARENT"]
    ann_id = r.json()["id"]

    def ids(token):
        return {a["id"] for a in client.get("/announcements", headers=auth(token)).json()}

    assert ann_id in ids(S["parent"]) and ann_id in ids(S["erkin"]) and ann_id in ids(S["director"])
    assert ann_id not in ids(S["teacher"])
    assert client.get(f"/announcements/{ann_id}", headers=auth(S["teacher"])).status_code == 404

    r = client.put(f"/announcements/{ann_id}", headers=auth(S["director"]), data={"audience": "ALL"})
    assert r.status_code == 200 and r.json()["audience"] is None
    assert ann_id in ids(S["teacher"])

    r = client.post("/announcements", headers=auth(S["director"]), data={"title": "Тест", "audience": "ALIENS"})
    assert r.status_code == 422
    assert client.delete(f"/announcements/{ann_id}", headers=auth(S["director"])).status_code == 200


def test_approve_marks_excused(client, freeze_time):
    frozen = freeze_time(10, 30)
    today = str(frozen.date())

    # Класс жетекчиге билдирүү келди
    r = client.get("/notifications/unread-count", headers=auth(S["teacher"]))
    assert r.json()["unread"] >= 2

    r = client.get("/absence-requests?status=PENDING", headers=auth(S["teacher"]))
    assert {x["id"] for x in r.json()} == {S["request"], S["request_tomorrow"]}

    # Класс жетекчи эмес мугалим жана директор беките албайт
    assert client.get("/absence-requests", headers=auth(S["teacher2"])).status_code == 403
    for token in (S["teacher2"], S["director"], S["parent"], S["erkin"]):
        r = client.post(f"/absence-requests/{S['request']}/approve", headers=auth(token))
        assert r.status_code == 403

    # Директор көзөмөлдөйт (көрөт)
    r = client.get("/absence-requests", headers=auth(S["director"]))
    assert r.status_code == 200 and len(r.json()) == 2

    r = client.post(f"/absence-requests/{S['request']}/approve", headers=auth(S["teacher"]))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "APPROVED" and r.json()["journal_entries_marked"] == 1

    r = client.post(f"/absence-requests/{S['request']}/approve", headers=auth(S["teacher"]))
    assert r.status_code == 400

    # Журналда автоматтык «С», XP кайра эсептелди
    r = client.get(f"/journal?assignment_id={S['assignment']}&day={today}", headers=auth(S["teacher"]))
    row = next(x for x in r.json()["students"] if x["student_id"] == S["erkin_id"])
    assert row["attendance"] == "С" and row["grade_value"] is None and row["excused"] is True

    r = client.get("/ratings/me", headers=auth(S["erkin"]))
    assert r.json()["total_xp"] == 0

    # Себептүү сураган окуучуга баа коюлбайт
    r = client.put("/journal", headers=auth(S["teacher"]), json={
        "assignment_id": S["assignment"], "date": today,
        "entries": [{"student_id": S["erkin_id"], "grade_value": 5}]})
    assert r.status_code == 400

    # Четке кагуу жана ата-энеге билдирүү
    r = client.post(f"/absence-requests/{S['request_tomorrow']}/reject",
                    headers=auth(S["teacher"]), json={"comment": "Документ жок"})
    assert r.status_code == 200 and r.json()["status"] == "REJECTED"

    r = client.get("/notifications", headers=auth(S["parent"]))
    titles = [n["title"] for n in r.json()]
    assert "Сурануу кабыл алынды" in titles and "Сурануу четке кагылды" in titles


def test_excused_applies_to_later_entries(client, freeze_time):
    """Бекитилген суранууга кийин киргизилген жазуу да автоматтык «С» болот."""
    frozen = freeze_time(7, 0, days=1)
    tomorrow = str(frozen.date())

    r = client.post("/absence-requests", headers=auth(S["parent"]),
                    json={"student_id": S["bekzat_id"], "reason": "Оору"})
    assert r.status_code == 201, r.text
    r = client.post(f"/absence-requests/{r.json()['id']}/approve", headers=auth(S["teacher"]))
    assert r.status_code == 200 and r.json()["journal_entries_marked"] == 0

    freeze_time(11, 0, days=1)
    r = client.put("/journal", headers=auth(S["teacher"]), json={
        "assignment_id": S["assignment"], "date": tomorrow, "entries": [
            {"student_id": S["bekzat_id"], "attendance": "Б"},
            {"student_id": S["aidana_id"], "grade_value": 5, "attendance": "Б"},
        ]})
    assert r.status_code == 200, r.text

    r = client.get(f"/journal?assignment_id={S['assignment']}&day={tomorrow}", headers=auth(S["teacher"]))
    row = next(x for x in r.json()["students"] if x["student_id"] == S["bekzat_id"])
    assert row["attendance"] == "С"


# =====================================================
# 4. Рейтинг, значоктор, олимпиада
# =====================================================

def test_ratings_badges_olympiad(client):
    # XP: Бекзат 35, Айдана -20+55 = 35, Эркин 0
    r = client.get("/ratings/parallel/11", headers=auth(S["erkin"]))
    assert r.status_code == 200
    ranks = {i["student_id"]: i["rank"] for i in r.json()["items"]}
    assert ranks[S["bekzat_id"]] == 1 and ranks[S["aidana_id"]] == 1 and ranks[S["erkin_id"]] == 3

    assert client.get("/ratings/school", headers=auth(S["parent"])).status_code == 200
    assert client.get(f"/ratings/subjects/{S['subject']}", headers=auth(S["erkin"])).status_code == 200

    # Топ — завуч/мугалим үчүн гана
    r = client.get(f"/ratings/subjects/{S['subject']}/top", headers=auth(S["erkin"]))
    assert r.status_code == 403
    r = client.get(f"/ratings/subjects/{S['subject']}/top", headers=auth(S["teacher"]))
    assert r.status_code == 200 and len(r.json()["items"]) == 2

    r = client.get(f"/profiles/students/{S['bekzat_id']}", headers=auth(S["parent"]))
    badges = {b["badge_type"] for b in r.json()["badges"]}
    assert {"SUBJECT_LEADER", "PARALLEL_CHAMP", "OLYMPIAD_CANDIDATE", "PERFECT_ATTENDANCE"} <= badges

    # Айдана кечиккен («К») — чагылган жок
    r = client.get(f"/profiles/students/{S['aidana_id']}", headers=auth(S["teacher"]))
    assert "PERFECT_ATTENDANCE" not in {b["badge_type"] for b in r.json()["badges"]}

    # Ата-эне бөтөн баланын профилин көрбөйт
    r = client.get(f"/profiles/students/{S['aidana_id']}", headers=auth(S["parent"]))
    assert r.status_code == 403

    # Мугалим сунуштайт -> завуч бекитет
    r = client.post("/olympiad/candidates", headers=auth(S["teacher"]),
                    json={"subject_id": S["subject"], "student_id": S["erkin_id"]})
    assert r.status_code == 201 and r.json()["status"] == "SUGGESTED"
    r = client.post(f"/olympiad/candidates/{r.json()['id']}/approve", headers=auth(S["teacher"]))
    assert r.status_code == 403
    r = client.post("/olympiad/auto-select", headers=auth(S["director"]),
                    json={"subject_id": S["subject"]})
    assert r.status_code == 200 and len(r.json()["selected"]) == 2

    r = client.get("/olympiad/analytics", headers=auth(S["director"]))
    assert r.json()["subjects"][0]["top"][0]["candidate_status"] == "SELECTED"

    r = client.get("/dashboard/stats", headers=auth(S["erkin"]))
    assert r.json() == {"students": 3, "teachers": 2, "classes": 1, "olympiad_candidates": 2}

    r = client.post("/ratings/recompute", headers=auth(S["director"]))
    assert r.status_code == 200


# =====================================================
# 5. Үй тапшырма
# =====================================================

def test_homework_flow(client):
    form = {"assignment_id": str(S["assignment"]), "title": "№234, 235, 236 көнүгүүлөр"}
    files = [("files", ("page.png", PNG, "image/png")),
             ("files", ("formula.pdf", b"%PDF-1.4 test", "application/pdf"))]

    r = client.post("/homeworks", headers=auth(S["teacher2"]), data=form, files=files)
    assert r.status_code == 403
    r = client.post("/homeworks", headers=auth(S["erkin"]), data=form, files=files)
    assert r.status_code == 403

    # Кеңейтүүсү .png, бирок мазмуну сүрөт эмес
    r = client.post("/homeworks", headers=auth(S["teacher"]), data=form,
                    files=[("files", ("evil.png", b"<script>", "image/png"))])
    assert r.status_code == 400
    r = client.post("/homeworks", headers=auth(S["teacher"]), data=form,
                    files=[("files", ("run.exe", b"MZ", "application/octet-stream"))])
    assert r.status_code == 400

    r = client.post("/homeworks", headers=auth(S["teacher"]), data=form, files=files)
    assert r.status_code == 201, r.text
    hw = r.json()
    assert len(hw["image_urls"]) == 1 and len(hw["file_urls"]) == 1

    # Файл статикалык дарек аркылуу ачылат
    assert client.get(hw["image_urls"][0]).content == PNG

    r = client.get("/homeworks", headers=auth(S["erkin"]))
    assert len(r.json()) == 1 and r.json()[0]["is_submitted"] is False

    r = client.get(f"/homeworks?student_id={S['bekzat_id']}", headers=auth(S["parent"]))
    assert len(r.json()) == 1

    r = client.post(f"/homeworks/{hw['id']}/submit", headers=auth(S["erkin"]),
                    data={"text": "Аткардым"},
                    files=[("files", ("answer.png", PNG, "image/png"))])
    assert r.status_code == 200, r.text

    r = client.get(f"/homeworks/{hw['id']}", headers=auth(S["erkin"]))
    assert r.json()["is_submitted"] is True

    r = client.get(f"/homeworks/{hw['id']}/submissions", headers=auth(S["teacher"]))
    assert len(r.json()) == 1 and r.json()[0]["student_name"] == "Алиев Эркин"

    # Башка мектеп көрбөйт
    assert client.get(f"/homeworks/{hw['id']}", headers=auth(S["other_director"])).status_code == 404

    r = client.delete(f"/homeworks/{hw['id']}", headers=auth(S["teacher"]))
    assert r.status_code == 200


# =====================================================
# 6. Портал, жарыялар, профиль
# =====================================================

def test_portal_announcements_profile(client):
    r = client.post("/announcements", headers=auth(S["teacher"]), data={"title": "Олимпиада"})
    assert r.status_code == 403
    r = client.post("/announcements", headers=auth(S["director"]), data={
        "title": "Республикалык олимпиада", "body": "27-апрелде өтөт"},
        files={"image": ("cup.png", PNG, "image/png")})
    assert r.status_code == 201, r.text
    assert client.get("/announcements", headers=auth(S["erkin"])).json()[0]["title"] == "Республикалык олимпиада"
    assert client.get("/announcements", headers=auth(S["other_director"])).json() == []

    r = client.post("/schools/me/banner", headers=auth(S["director"]),
                    files={"file": ("banner.png", PNG, "image/png")})
    assert r.status_code == 200 and r.json()["banner_url"].endswith(".png")

    # Ачык баракчалар авторизациясыз
    assert client.get("/public/stats").json()["schools"] >= 2
    r = client.get("/public/schools?search=Тест мектеп №1")
    assert [s["id"] for s in r.json()] == [S["school"]]
    r = client.get(f"/public/schools/{S['school']}")
    assert r.json()["stats"]["students"] == 3 and len(r.json()["news"]) == 1

    r = client.post("/me/avatar", headers=auth(S["erkin"]),
                    files={"file": ("me.png", PNG, "image/png")})
    assert r.status_code == 200

    r = client.get("/me", headers=auth(S["erkin"]))
    assert r.json()["student"]["class_name"] == "11-А"

    r = client.post("/me/change-password", headers=auth(S["erkin"]),
                    json={"current_password": "NewPass#2026", "new_password": "Another#2026"})
    assert r.status_code == 200
    login(client, "u90000000000101@test.kg", "Another#2026")

    # Класс жетекчи окуучунун сыр сөзүн баштапкы абалга келтирет
    r = client.post(f"/classes/{S['class']}/students/{S['erkin_id']}/reset-password",
                    headers=auth(S["teacher"]))
    assert r.status_code == 200
    # Сыр сөз жаңыланды — эски токен иштебейт, окуучу кайра кирип, сыр сөзүн алмаштырат
    assert client.get("/me", headers=auth(S["erkin"])).status_code == 401
    S["erkin"] = login_and_change(client, "u90000000000101@test.kg", r.json()["temporary_password"])


# =====================================================
# 7. Мугалимдердин тизмеси жана предметтерди башкаруу
# =====================================================

def test_teachers_and_subjects_crud(client):
    h = auth(S["director"])

    r = client.get("/teachers", headers=h)
    assert r.status_code == 200, r.text
    teachers = {t["id"]: t for t in r.json()}
    assert set(teachers) == {S["teacher_id"], S["teacher2_id"]}
    lead = teachers[S["teacher_id"]]
    assert lead["is_class_teacher"] is True
    assert lead["classes_led"][0]["name"] == "11-А"
    assert lead["assignments"][0]["subject_name"] == "Кыргыз тили"
    assert "temporary_password" not in lead

    assert client.get("/teachers", headers=auth(S["teacher"])).status_code == 403
    assert client.get("/teachers", headers=auth(S["erkin"])).status_code == 403
    assert client.get(f"/teachers/{S['teacher_id']}", headers=auth(S["other_director"])).status_code == 404

    r = client.get("/teachers?search=Башка", headers=h)
    assert [t["id"] for t in r.json()] == [S["teacher2_id"]]

    r = client.put(f"/teachers/{S['teacher2_id']}", headers=h, json={"full_name": "Башка Мугалим Жаңы"})
    assert r.status_code == 200 and r.json()["full_name"] == "Башка Мугалим Жаңы"

    r = client.delete(f"/teachers/{S['teacher2_id']}", headers=h)
    assert r.status_code == 200
    assert S["teacher2_id"] not in [t["id"] for t in client.get("/teachers", headers=h).json()]
    r = client.get("/teachers?include_inactive=true", headers=h)
    assert next(t for t in r.json() if t["id"] == S["teacher2_id"])["is_active"] is False
    r = client.post(f"/teachers/{S['teacher2_id']}/activate", headers=h)
    assert r.status_code == 200 and r.json()["is_active"] is True

    # Предметтер
    # Тизмеде жок аталыш кабыл алынбайт
    assert client.post("/subjects/", headers=h, json={"name": "Кандайдыр сабак"}).status_code == 422
    r = client.post("/subjects/", headers=h, json={"name": "Дүйнөлүк тарых"})
    subject_id = r.json()["id"]
    r = client.put(f"/subjects/{subject_id}", headers=h, json={"name": "Кыргызстан тарыхы"})
    assert r.status_code == 200 and r.json()["name"] == "Кыргызстан тарыхы"
    r = client.put(f"/subjects/{subject_id}", headers=h, json={"name": "Кыргыз тили"})
    assert r.status_code == 400
    assert client.put(f"/subjects/{subject_id}", headers=auth(S["teacher"]), json={"code": "X"}).status_code == 403
    assert client.delete(f"/subjects/{S['subject']}", headers=h).status_code == 400
    assert client.delete(f"/subjects/{subject_id}", headers=h).status_code == 200


# =====================================================
# 8. Сабактардын жадыбалы
# =====================================================

def test_schedule(client):
    from datetime import date, timedelta

    h = auth(S["director"])

    # Кошумча класс, предмет жана бекитүүлөр
    r = client.post("/classes/", headers=h, json={
        "grade_number": 11, "letter": "Б", "academic_year": "2026-2027"})
    class_b = r.json()["id"]
    r = client.post("/subjects/", headers=h, json={"name": "Математика"})
    math = r.json()["id"]
    kg_a = S["assignment"]  # 11-А, Кыргыз тили, teacher
    kg_b = client.post("/admin/teacher-assignments", headers=h, json={
        "teacher_id": S["teacher_id"], "class_id": class_b, "subject_id": S["subject"]}).json()["id"]
    math_a = client.post("/admin/teacher-assignments", headers=h, json={
        "teacher_id": S["teacher2_id"], "class_id": S["class"], "subject_id": math}).json()["id"]

    r = client.get("/schedule/bells", headers=auth(S["erkin"]))
    assert r.json()["bells"][0] == {"lesson_number": 1, "start_time": "08:00", "end_time": "08:45"}

    # Директор/завуч гана түзөт
    body = {"assignment_id": kg_a, "weekday": 1, "lesson_number": 1, "room": "101"}
    for token in (S["teacher"], S["erkin"], S["parent"]):
        assert client.post("/schedule", headers=auth(token), json=body).status_code == 403

    r = client.post("/schedule", headers=h, json=body)
    assert r.status_code == 201, r.text
    lesson_a = r.json()
    assert lesson_a["start_time"] == "08:00" and lesson_a["class_name"] == "11-А"
    assert lesson_a["teacher_name"] == "Класс Жетекчи Мугалим"

    # Класстын бир убакта эки сабагы болбойт
    r = client.post("/schedule", headers=h, json={"assignment_id": math_a, "weekday": 1, "lesson_number": 1})
    assert r.status_code == 409 and "11-А" in r.json()["detail"]

    # Мугалим бир убакта эки класста болбойт
    r = client.post("/schedule", headers=h, json={"assignment_id": kg_b, "weekday": 1, "lesson_number": 1})
    assert r.status_code == 409 and "Мугалим" in r.json()["detail"]

    # Кабинет бош эмес
    r = client.post("/schedule", headers=h, json={
        "assignment_id": math_a, "weekday": 1, "lesson_number": 2, "room": "101"})
    assert r.status_code == 201, r.text
    r = client.post("/schedule", headers=h, json={
        "assignment_id": kg_b, "weekday": 1, "lesson_number": 2, "room": "101"})
    assert r.status_code == 409 and "кабинет" in r.json()["detail"]

    # Өз убактысы менен; кесилишкен убакыт — 409
    r = client.post("/schedule", headers=h, json={
        "assignment_id": kg_b, "weekday": 2, "lesson_number": 1,
        "start_time": "09:00", "end_time": "09:45"})
    assert r.status_code == 201 and r.json()["start_time"] == "09:00"
    r = client.post("/schedule", headers=h, json={
        "assignment_id": kg_a, "weekday": 2, "lesson_number": 2,
        "start_time": "09:30", "end_time": "10:15"})
    assert r.status_code == 409
    r = client.post("/schedule", headers=h, json={
        "assignment_id": kg_a, "weekday": 2, "lesson_number": 3,
        "start_time": "10:00", "end_time": "09:00"})
    assert r.status_code == 400

    # Өзгөртүү
    r = client.put(f"/schedule/{lesson_a['id']}", headers=h, json={"lesson_number": 2})
    assert r.status_code == 409
    r = client.put(f"/schedule/{lesson_a['id']}", headers=h, json={"weekday": 3})
    assert r.status_code == 200 and r.json()["weekday_name"] == "Шаршемби"
    r = client.put(f"/schedule/{lesson_a['id']}", headers=h, json={"assignment_id": kg_b})
    assert r.status_code == 400
    assert client.put(f"/schedule/{lesson_a['id']}", headers=auth(S["teacher"]),
                      json={"room": "1"}).status_code == 403

    # Көрүү
    r = client.get(f"/schedule/class/{S['class']}", headers=auth(S["erkin"]))
    assert [(x["weekday"], x["lesson_number"]) for x in r.json()["lessons"]] == [(1, 2), (3, 1)]

    r = client.get(f"/schedule/teacher/{S['teacher_id']}", headers=auth(S["director"]))
    assert {x["class_name"] for x in r.json()["lessons"]} == {"11-А", "11-Б"}

    r = client.get("/schedule/me", headers=auth(S["teacher"]))
    assert len(r.json()["lessons"]) == 2

    wednesday = date.today() + timedelta(days=(3 - date.today().isoweekday()) % 7)
    r = client.get(f"/schedule/me?day={wednesday}", headers=auth(S["erkin"]))
    assert [x["subject_name"] for x in r.json()["lessons"]] == ["Кыргыз тили"]
    r = client.get(f"/schedule/me?student_id={S['bekzat_id']}", headers=auth(S["parent"]))
    assert len(r.json()["lessons"]) == 2
    sunday = date.today() + timedelta(days=(7 - date.today().isoweekday()) % 7)
    assert client.get(f"/schedule/me?day={sunday}", headers=auth(S["erkin"])).json()["lessons"] == []
    assert client.get("/schedule/today", headers=auth(S["erkin"])).status_code == 200

    assert client.get(f"/schedule/class/{S['class']}", headers=auth(S["other_director"])).status_code == 404

    # Өчүрүү
    assert client.delete(f"/schedule/{lesson_a['id']}", headers=auth(S["teacher"])).status_code == 403
    assert client.delete(f"/schedule/{lesson_a['id']}", headers=h).status_code == 200


# =====================================================
# 9. Платформанын администратору (SYSTEM_ADMIN)
# =====================================================

def test_login_rate_limit(client):
    from mysite.security import login_limit

    email = "u90000000000999@test.kg"
    try:
        for _ in range(login_limit.MAX_FAILURES_PER_LOGIN):
            r = client.post("/auth/login", json={"email": email, "password": "wrong-password"})
            assert r.status_code == 401
        r = client.post("/auth/login", json={"email": email, "password": "wrong-password"})
        assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0
    finally:
        login_limit.reset(email)
        login_limit._failures.clear()


def test_system_admin(client, db):
    from mysite.services.passwords import set_temp_password

    admin = Users(email="u90000000000900@test.kg", full_name="Платформа Админ", role="SYSTEM_ADMIN",
                  hashed_password="", school_id=None)
    temp = set_temp_password(admin)
    db.add(admin)
    db.commit()

    sa = auth(login_and_change(client, "u90000000000900@test.kg", temp))

    r = client.get("/me", headers=sa)
    assert r.status_code == 200 and r.json()["role"] == "SYSTEM_ADMIN" and r.json()["school"] is None

    # Мектеп администраторлору /system жабык
    for token in (S["director"], S["teacher"], S["erkin"], S["parent"]):
        assert client.get("/system/schools", headers=auth(token)).status_code == 403

    r = client.get("/system/schools", headers=sa)
    assert r.status_code == 200
    mine = next(s for s in r.json() if s["id"] == S["school"])
    assert mine["stats"]["students"] == 3

    # Жаңы мектеп + директор
    r = client.post("/system/schools", headers=sa, json={
        "name": "Тест мектеп №3",
        "director": {"email": "u90000000000301@test.kg", "full_name": "Үчүнчү Директор"}})
    assert r.status_code == 201, r.text
    new_school = r.json()["school"]["id"]
    new_director_pw = r.json()["director"]["temporary_password"]
    assert r.json()["school"]["director_name"] == "Үчүнчү Директор"

    # Почта кайталанса мектеп да түзүлбөйт
    r = client.post("/system/schools", headers=sa, json={
        "name": "Кайталанма мектеп", "director": {"email": "u90000000000301@test.kg", "full_name": "Дагы Директор"}})
    assert r.status_code == 400
    assert not [s for s in client.get("/system/schools?search=Кайталанма", headers=sa).json()]

    # Жаңы директор кирип, өз мектебин гана көрөт
    d3 = auth(login_and_change(client, "u90000000000301@test.kg", new_director_pw))
    assert client.get("/schools/me", headers=d3).json()["id"] == new_school
    assert client.get(f"/classes/{S['class']}", headers=d3).status_code == 404

    # Директор завуч кошот, завуч киргенде админ укуктары бар
    r = client.post("/admin/deputies", headers=d3, json={"email": "u90000000000302@test.kg", "full_name": "Үчүнчү Завуч"})
    assert r.status_code == 201, r.text
    deputy_id, deputy_pw = r.json()["id"], r.json()["temporary_password"]
    dep = auth(login_and_change(client, "u90000000000302@test.kg", deputy_pw))
    assert client.post("/classes/", headers=dep, json={
        "grade_number": 5, "letter": "А", "academic_year": "2026-2027"}).status_code == 200
    # Завуч башка завуч кошо албайт, тизмеде сыр сөздөрдү көрбөйт
    assert client.post("/admin/deputies", headers=dep, json={
        "email": "u90000000000303@test.kg", "full_name": "Дагы Завуч"}).status_code == 403
    assert client.get("/admin/deputies", headers=dep).json()[0]["temporary_password"] is None
    # Директор завучтун сыр сөзүн жаңырта алат
    r = client.post(f"/admin/users/{deputy_id}/reset-password", headers=d3)
    assert r.status_code == 200
    # Эски сессия жабылды — завуч жаңы убактылуу сыр сөз менен кайра кирет
    assert client.get("/me", headers=dep).status_code == 401
    dep = auth(login_and_change(client, "u90000000000302@test.kg", r.json()["temporary_password"]))

    # Мектепти жабуу: колдонуучулары кире албайт
    assert client.post(f"/system/schools/{new_school}/deactivate", headers=sa).status_code == 200
    assert client.get("/me", headers=d3).status_code == 403
    assert client.post(f"/system/schools/{new_school}/activate", headers=sa).status_code == 200
    assert client.get("/me", headers=d3).status_code == 200

    # Директордун сыр сөзүн платформанын админи гана жаңыртат
    d3_id = next(a["id"] for a in client.get(f"/system/schools/{new_school}", headers=sa).json()["admins"]
                 if a["role"] == "DIRECTOR")
    assert client.post(f"/admin/users/{d3_id}/reset-password", headers=dep).status_code == 400
    r = client.post(f"/system/users/{d3_id}/reset-password", headers=sa)
    assert r.status_code == 200 and r.json()["temporary_password"]
    d3 = auth(login_and_change(client, "u90000000000301@test.kg", r.json()["temporary_password"]))

    # Бар мектепке кошумча директор/завуч
    r = client.post(f"/system/schools/{S['school']}/admins", headers=sa, json={
        "email": "u90000000000003@test.kg", "full_name": "Биринчи Завуч", "role": "DEPUTY"})
    assert r.status_code == 201 and r.json()["role"] == "DEPUTY"

    # Чектөөлөр: бир директор, эң көп 5 завуч (активдүүлөр гана саналат)
    r = client.post(f"/system/schools/{new_school}/admins", headers=sa, json={
        "email": "u90000000000310@test.kg", "full_name": "Экинчи Директор", "role": "DIRECTOR"})
    assert r.status_code == 400

    deputy_ids = [deputy_id]
    for index, surname in enumerate(["Экинчи", "Үчүнчү", "Төртүнчү", "Бешинчи"]):
        r = client.post("/admin/deputies", headers=d3, json={
            "email": f"u9000000000032{index}@test.kg", "full_name": f"{surname} Завуч"})
        assert r.status_code == 201, r.text
        deputy_ids.append(r.json()["id"])

    r = client.post("/admin/deputies", headers=d3, json={"email": "u90000000000329@test.kg", "full_name": "Алтынчы Завуч"})
    assert r.status_code == 400
    r = client.post(f"/system/schools/{new_school}/admins", headers=sa, json={
        "email": "u90000000000329@test.kg", "full_name": "Алтынчы Завуч", "role": "DEPUTY"})
    assert r.status_code == 400

    # Бирин өчүргөндөн кийин жаңысын кошсо болот, ал эми өчүрүлгөнүн кайра күйгүзүүгө болбойт
    assert client.delete(f"/admin/deputies/{deputy_ids[-1]}", headers=d3).status_code == 200
    assert client.post("/admin/deputies", headers=d3, json={
        "email": "u90000000000329@test.kg", "full_name": "Алтынчы Завуч"}).status_code == 201
    assert client.post(f"/system/users/{deputy_ids[-1]}/activate", headers=sa).status_code == 400
    # Директор да 5 завуч толуп турганда өчүрүлгөндү кайра күйгүзө албайт
    assert client.post(f"/admin/deputies/{deputy_ids[-1]}/activate", headers=d3).status_code == 400

    # Директор өз завучунун аты-жөнүн өзгөртөт
    r = client.put(f"/admin/deputies/{deputy_ids[1]}", headers=d3,
                   json={"full_name": "Жаңы Аты Завуч"})
    assert r.status_code == 200, r.text
    assert r.json()["full_name"] == "Жаңы Аты Завуч"
    # Башка мектептин директору жана завучтун өзү өзгөртө албайт
    assert client.put(f"/admin/deputies/{deputy_ids[1]}", headers=auth(S["director"]),
                      json={"full_name": "Бөтөн"}).status_code == 404
    assert client.put(f"/admin/deputies/{deputy_ids[1]}", headers=dep,
                      json={"full_name": "Өзү"}).status_code == 403
    # Бирин өчүрсө, мурда өчүрүлгөнүн кайра күйгүзсө болот
    assert client.delete(f"/admin/deputies/{deputy_ids[1]}", headers=d3).status_code == 200
    assert client.post(f"/admin/deputies/{deputy_ids[-1]}/activate", headers=d3).status_code == 200

    # Директорду өчүрүп, ордуна жаңысын дайындоо
    assert client.post(f"/system/users/{d3_id}/deactivate", headers=sa).status_code == 200
    r = client.post(f"/system/schools/{new_school}/admins", headers=sa, json={
        "email": "u90000000000310@test.kg", "full_name": "Экинчи Директор", "role": "DIRECTOR"})
    assert r.status_code == 201, r.text
    assert client.post(f"/system/users/{d3_id}/activate", headers=sa).status_code == 400

    r = client.get("/system/stats", headers=sa)
    assert r.json()["schools"] >= 3 and r.json()["deputies"] >= 2


# =====================================================
# Окуучуларды автоматтык өткөрүү жана кийин класстарын оңдоо
# =====================================================

def test_promotion_auto_then_move(client, db):
    school = Schools(name="Өткөрүү тест мектеби")
    db.add(school)
    db.flush()
    db.add(Users(email="promo.director@test.kg", full_name="Өткөрүү Директор", role="DIRECTOR",
                 hashed_password=hash_password("Mektep#2026"), school_id=school.id,
                 is_temp_password=False))
    db.commit()
    h = auth(login(client, "promo.director@test.kg", "Mektep#2026")["access_token"])

    class_ids = {}
    for grade in (5, 11):
        r = client.post("/classes/", headers=h, json={
            "grade_number": grade, "letter": "А", "academic_year": "2030-2031"})
        assert r.status_code == 200, r.text
        class_ids[grade] = r.json()["id"]

    student_ids = {}
    for email, name, grade in (
        ("promo.a@test.kg", "Асанов Алмаз", 5),
        ("promo.b@test.kg", "Бакиров Бекжан", 5),
        ("promo.c@test.kg", "Чынгызова Чолпон", 11),
    ):
        r = client.post("/students/", headers=h, json={
            "email": email, "full_name": name, "class_id": class_ids[grade]})
        assert r.status_code == 200, r.text
        student_ids[email] = r.json()["id"]

    # Өткөрүүгө чейин жыйынтык бош
    r = client.get("/students/promotion/review?target_academic_year=2031-2032", headers=h)
    assert r.status_code == 200 and r.json()["students"] == []

    r = client.post("/students/promotion/execute", headers=h, json={
        "source_academic_year": "2030-2031", "target_academic_year": "2031-2032"})
    assert r.status_code == 200, r.text
    assert r.json()["promoted"] == 2 and r.json()["graduated"] == 1

    review = {s["student_id"]: s for s in client.get(
        "/students/promotion/review?target_academic_year=2031-2032", headers=h).json()["students"]}
    assert review[student_ids["promo.a@test.kg"]]["to_class"] == "6-А"
    assert review[student_ids["promo.c@test.kg"]]["to_class"] is None

    # Бир окуучу 5-класста калат (класс жаңы окуу жылында түзүлөт), бүтүрүүчү 11-класста калат
    for email, grade in (("promo.b@test.kg", 5), ("promo.c@test.kg", 11)):
        r = client.put("/students/promotion/move", headers=h, json={
            "student_id": student_ids[email], "target_academic_year": "2031-2032",
            "grade_number": grade, "letter": "А"})
        assert r.status_code == 200, r.text

    review = {s["student_id"]: s for s in client.get(
        "/students/promotion/review?target_academic_year=2031-2032", headers=h).json()["students"]}
    assert review[student_ids["promo.b@test.kg"]]["to_class"] == "5-А"
    assert review[student_ids["promo.c@test.kg"]]["to_class"] == "11-А"

    # Өткөрүүгө катышпаган окуучуну которууга болбойт
    r = client.put("/students/promotion/move", headers=h, json={
        "student_id": student_ids["promo.a@test.kg"], "target_academic_year": "2035-2036",
        "grade_number": 7, "letter": "А"})
    assert r.status_code == 400


# =====================================================
# Ата-эне коду, почтаны алмаштыруу, сыр сөздү калыбына келтирүү
# =====================================================

def test_parent_code_after_student_changed_password(client):
    # Эркин сыр сөзүн мурда эле алмаштырган — ата-эне баары бир код менен байланат
    erkin = S["students"]["u90000000000101@test.kg"]
    r = client.post("/parents/register", json={
        "email": "code.parent@test.kg", "full_name": "Коддуу Ата-эне", "password": "Parent#2026",
        "student_code": erkin["parent_code"].lower()[:4] + "-" + erkin["parent_code"][4:]})
    assert r.status_code == 200, r.text

    # Кодду жаңыласа, эскиси иштебей калат
    r = client.post(f"/classes/{S['class']}/students/{erkin['id']}/parent-code", headers=auth(S["teacher"]))
    assert r.status_code == 200 and r.json()["parent_code"] != erkin["parent_code"]
    r = client.post("/parents/register", json={
        "email": "old.code@test.kg", "full_name": "Эски Код", "password": "Parent#2026",
        "student_code": erkin["parent_code"]})
    assert r.status_code == 404


def test_change_email_and_reset_password(client, db):
    from mysite.api.auth import create_reset_token

    h = auth(S["director"])
    aidana_id = S["aidana_id"]
    r = client.put(f"/students/{aidana_id}", headers=h, json={"email": "Aidana.New@Test.kg"})
    assert r.status_code == 200, r.text
    # Бош эмес почтага алмаштырууга болбойт
    r = client.put(f"/students/{aidana_id}", headers=h, json={"email": "u90000000000101@test.kg"})
    assert r.status_code == 400

    aidana = db.query(Users).filter(Users.id == aidana_id).first()
    assert aidana.email == "aidana.new@test.kg"

    # Белгисиз почтага да жооп бирдей
    assert client.post("/auth/forgot-password", json={"email": "nobody@test.kg"}).status_code == 200
    assert client.post("/auth/forgot-password", json={"email": "aidana.new@test.kg"}).status_code == 200

    token = create_reset_token(aidana)
    # Шилтеменин токени менен API'ге кирүүгө болбойт
    assert client.get("/me", headers=auth(token)).status_code == 401

    r = client.post("/auth/reset-password", json={"token": token, "new_password": "Reset#2026"})
    assert r.status_code == 200, r.text
    assert login(client, "aidana.new@test.kg", "Reset#2026")["requires_password_change"] is False
    # Шилтеме бир гана жолу иштейт
    r = client.post("/auth/reset-password", json={"token": token, "new_password": "Again#2026"})
    assert r.status_code == 400


def test_new_student_has_parent_code_and_banner_position_saved(client, db):
    h = auth(S["director"])
    r = client.post("/students/", headers=h, json={
        "email": "fresh.student@test.kg", "full_name": "Жаңы Окуучу", "class_id": S["class"]})
    assert r.status_code == 200, r.text
    student = db.query(Users).filter(Users.id == r.json()["id"]).first()
    # Код класс жетекчи тизмени ачканга чейин эле бар
    assert student.parent_code and len(student.parent_code) == 8

    position = {"url": "/media/banner.png", "x": 30, "y": 80}
    r = client.put("/me", headers=h, json={"banner_position": position})
    assert r.status_code == 200 and r.json()["banner_position"] == position
    assert client.put("/me", headers=h, json={"banner_position": {"url": "/x.png", "x": 150, "y": 0}}).status_code == 422
    r = client.put("/me", headers=h, json={"banner_position": None})
    assert r.json()["banner_position"] is None


# =====================================================
# Окуу программасы
# =====================================================

def program_excel(rows):
    wb = Workbook()
    ws = wb.active
    ws.append(["Бөлүм", "Тема", "Саат", "Апта", "Максаттар", "Материалдар"])
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_curriculum_program(client):
    h = auth(S["director"])
    t = auth(S["teacher"])
    first = client.get("/programs", headers=t).json()["items"][0]
    subject_id, class_id, grade = first["subject_id"], first["class_id"], first["grade_number"]
    assert first["has_program"] is False

    # Ката бар файл эч нерсени өзгөртпөйт
    r = client.post("/programs/import", headers=h, data={"subject_id": subject_id, "grade_number": grade},
                    files={"file": ("p.xlsx", program_excel([["Бөлүм", "", 1, 1, "", ""]]), XLSX)})
    assert r.status_code == 400

    r = client.post("/programs/import", headers=h, data={"subject_id": subject_id, "grade_number": grade},
                    files={"file": ("p.xlsx", program_excel([
                        ["Кириш", "Биринчи тема", 2, 1, "Максат", "Китеп"],
                        ["Кириш", "Экинчи тема", 1, 2, None, None],
                    ]), XLSX)})
    assert r.status_code == 200 and r.json()["topics_count"] == 2, r.text

    # Мугалим өз класстарын жана программасын көрөт
    cards = client.get("/programs", headers=t).json()["items"]
    card = next(c for c in cards if c["subject_id"] == subject_id and c["class_id"] == class_id)
    assert card["has_program"] and card["total"] == 2 and card["done"] == 0

    url = f"/programs/class/{class_id}/subject/{subject_id}"
    topics = client.get(url, headers=t).json()["topics"]
    r = client.put(f"{url}/topics/{topics[0]['id']}", headers=t, json={"done": True, "note": "Жакшы өттү"})
    assert r.status_code == 200 and r.json()["done_on"]
    assert client.get(url, headers=t).json()["topics"][0]["note"] == "Жакшы өттү"

    # Бул классты окутпаган мугалим жана окуучу белгилей албайт
    assert client.put(f"{url}/topics/{topics[0]['id']}", headers=auth(S["teacher2"]), json={"done": True}).status_code in (401, 403)
    assert client.get(url, headers=auth(S["erkin"])).status_code == 403

    r = client.put(f"{url}/topics/{topics[0]['id']}", headers=t, json={"done": False})
    assert r.status_code == 200 and r.json()["done_on"] is None

    assert client.get("/admin/excel/templates/program", headers=h).content[:2] == b"PK"


# =====================================================
# Хакердин көз карашы: башка мектептин жана башка ролдун маалыматына жетүү аракеттери
# =====================================================

def test_attacker_cannot_reach_foreign_data(client):
    d = auth(S["director"])
    ids = {
        "class": S["class"],
        "student": S["bekzat_id"],
        "teacher": S["teacher_id"],
        "subject": client.get("/subjects/", headers=d).json()[0]["id"],
        "assignment": S["assignment"],
        "request": S["request"],
        "announcement": (client.get("/announcements", headers=d).json() or [{"id": 999999}])[0]["id"],
        "homework": (client.get("/homeworks", headers=d).json() or [{"id": 999999}])[0]["id"],
        "notification": 1,
    }
    lessons = client.get(f"/schedule/class/{ids['class']}", headers=d).json()
    ids["lesson"] = lessons[0]["id"] if isinstance(lessons, list) and lessons else 999999

    probes = [
        ("get", "/classes/{class}"), ("put", "/classes/{class}"), ("delete", "/classes/{class}"),
        ("put", "/classes/{class}/class-teacher"), ("get", "/classes/{class}/temp-passwords"),
        ("post", "/classes/{class}/students/{student}/reset-password"),
        ("post", "/classes/{class}/students/{student}/parent-code"),
        ("get", "/students/{student}"), ("put", "/students/{student}"), ("delete", "/students/{student}"),
        ("get", "/students/{student}/history"), ("get", "/students/class/{class}"),
        ("get", "/profiles/students/{student}"), ("get", "/teachers/{teacher}"), ("put", "/teachers/{teacher}"),
        ("delete", "/teachers/{teacher}"), ("post", "/teachers/{teacher}/activate"),
        ("get", "/subjects/{subject}"), ("put", "/subjects/{subject}"), ("delete", "/subjects/{subject}"),
        ("delete", "/teacher-assignments/{assignment}"), ("get", "/teacher-assignments/teacher/{teacher}"),
        ("get", "/absence-requests/{request}"), ("post", "/absence-requests/{request}/approve"),
        ("post", "/absence-requests/{request}/reject"), ("post", "/absence-requests/{request}/cancel"),
        ("get", "/announcements/{announcement}"), ("put", "/announcements/{announcement}"),
        ("delete", "/announcements/{announcement}"),
        ("get", "/homeworks/{homework}"), ("put", "/homeworks/{homework}"), ("delete", "/homeworks/{homework}"),
        ("get", "/homeworks/{homework}/submissions"),
        ("get", "/journal/class/{class}"), ("get", "/ratings/class/{class}"),
        ("get", "/schedule/class/{class}"), ("get", "/schedule/teacher/{teacher}"),
        ("put", "/schedule/{lesson}"), ("delete", "/schedule/{lesson}"),
        ("post", "/admin/users/{teacher}/reset-password"), ("get", "/users/{teacher}"),
        ("post", "/users/{teacher}/reset-password"),
        ("get", "/programs/class/{class}/subject/{subject}"),
        ("post", "/notifications/{notification}/read"),
    ]
    bodies = {"put": {"full_name": "Бузулду Аты", "name": "Бузулду", "title": "x", "text": "x"}, "post": {}}
    attackers = {"other_school_director": auth(S["other_director"]), "student": auth(S["erkin"])}
    # Окуучуга атайын ачык: өз классы, жадыбал, рейтинг жана классташтын рейтинг-профили (почтасыз),
    # предмет, мугалимдин аты жана жадыбалы. Почталар жана тарых жабык.
    allowed_for_student = {"/schedule/class/{class}", "/ratings/class/{class}", "/homeworks/{homework}",
                           "/announcements/{announcement}", "/notifications/{notification}/read",
                           "/classes/{class}", "/profiles/students/{student}", "/subjects/{subject}",
                           "/schedule/teacher/{teacher}", "/users/{teacher}"}

    leaks = []
    for who, headers in attackers.items():
        for method, template in probes:
            if who == "student" and template in allowed_for_student:
                continue
            path = template.format(**ids)
            kwargs = {"headers": headers}
            if method in bodies:
                kwargs["json"] = bodies[method]
            response = getattr(client, method)(path, **kwargs)
            if 200 <= response.status_code < 300:
                leaks.append(f"{who}: {method.upper()} {path} -> {response.status_code}")
    assert not leaks, "\n".join(leaks)


def test_old_tokens_stop_working_after_password_change(client):
    # Токен уурдалды дейли: ээси сыр сөзүн алмаштырганда уурдалган токен иштебей калышы керек

    erkin_token = S["erkin"]
    assert client.get("/me", headers=auth(erkin_token)).status_code == 200

    r = client.post("/me/change-password", headers=auth(erkin_token),
                    json={"current_password": "NewPass#2026", "new_password": "Changed#2026"})
    assert r.status_code == 200, r.text
    assert client.get("/me", headers=auth(erkin_token)).status_code == 401

    S["erkin"] = login(client, "u90000000000101@test.kg", "Changed#2026")["access_token"]
    assert client.get("/me", headers=auth(S["erkin"])).status_code == 200

    # Логотипти каалаган шилтемеге алмаштырууга болбойт (файл жүктөө гана)
    client.put("/schools/me", headers=auth(S["director"]), json={"name": "Тест мектеп №1", "logo_url": "https://evil.example/x.png"})
    assert client.get("/schools/me", headers=auth(S["director"])).json()["logo_url"] != "https://evil.example/x.png"


def test_password_edge_cases(client):
    # Өтө узун сыр сөз сервердин катасына (500) алып келбейт
    r = client.post("/auth/login", json={"email": "u90000000000101@test.kg", "password": "a" * 100})
    assert r.status_code in (401, 422)
    r = client.post("/auth/login", json={"email": "u90000000000101@test.kg", "password": "я" * 60})
    assert r.status_code == 401

    # Жөнөкөй сыр сөзгө алмаштырууга болбойт
    h = auth(S["erkin"])
    for weak in ("12345678", "abcdefgh", "password1", "aaaa1111"):
        r = client.post("/me/change-password", headers=h,
                        json={"current_password": "Changed#2026", "new_password": weak})
        assert r.status_code == 422, (weak, r.text)


def test_homework_files_need_signed_link(client):
    from mysite.services.files import MEDIA_ROOT, sign_media_url

    path = MEDIA_ROOT / "submissions" / "999"
    path.mkdir(parents=True, exist_ok=True)
    (path / "work.pdf").write_bytes(b"%PDF-1.4 secret homework")
    url = "/media/submissions/999/work.pdf"

    # Колсуз жана жасалма кол менен — жок
    assert client.get(url).status_code == 404
    assert client.get(url + "?exp=99999999999&sig=0000").status_code == 404
    # Мөөнөтү өткөн шилтеме — жок
    signed = sign_media_url(url)
    expired = signed.replace(signed.split("exp=")[1].split("&")[0], "1000")
    assert client.get(expired).status_code == 404
    # API берген шилтеме — ачылат
    assert client.get(signed).content.startswith(b"%PDF")
    # Мектептин сүрөттөрү сыяктуу ачык файлдар мурдагыдай ачык
    assert sign_media_url("/media/avatars/1/a.png") == "/media/avatars/1/a.png"


def test_proxy_secret_blocks_direct_access(client, monkeypatch):
    from mysite.security import login_limit

    monkeypatch.setattr(login_limit, "PROXY_SECRET", "test-proxy-secret")
    # Түз кирүү (ачкычсыз) жабык, /health ачык
    assert client.post("/auth/login", json={"email": "a@test.kg", "password": "x"}).status_code == 403
    assert client.get("/health").status_code == 200

    # Сайт аркылуу: IP Vercel'ден келет, жасалма X-Forwarded-For эсепке алынбайт
    proxy = {"x-proxy-secret": "test-proxy-secret", "x-client-ip": "203.0.113.7", "x-forwarded-for": "1.2.3.4"}
    for _ in range(login_limit.MAX_FAILURES_PER_IP):
        login_limit.record_failure("spray", "203.0.113.7")
    r = client.post("/auth/login", headers=proxy, json={"email": "new.victim@test.kg", "password": "Wrong#2026"})
    assert r.status_code == 429
    login_limit._failures.clear()

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


def login(client, inn, password):
    r = client.post("/auth/login", json={"inn": inn, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def login_and_change(client, inn, temp_password, new_password="NewPass#2026"):
    data = login(client, inn, temp_password)
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
    ws.append(["ИНН", "Толук аты-жөнү", "Телефон"])
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
        school = Schools(name=name, address="Бишкек")
        db.add(school)
        db.flush()
        S[key] = school.id

    db.add(Users(inn="90000000000001", full_name="Тест Директор", role="DIRECTOR",
                 hashed_password=hash_password("Mektep#2026"), school_id=S["school"]))
    db.add(Users(inn="90000000000002", full_name="Башка Директор", role="DIRECTOR",
                 hashed_password=hash_password("Mektep#2026"), school_id=S["other_school"],
                 is_temp_password=False))
    db.commit()

    S["director"] = login_and_change(client, "90000000000001", "Mektep#2026")
    S["other_director"] = login(client, "90000000000002", "Mektep#2026")["access_token"]


def test_class_subject_teachers(client):
    h = auth(S["director"])

    r = client.post("/classes/", headers=h, json={
        "grade_number": 11, "letter": "А", "academic_year": "2026-2027"})
    assert r.status_code == 200, r.text
    S["class"] = r.json()["id"]

    r = client.post("/subjects/", headers=h, json={"name": "Кыргыз тили", "code": "KG"})
    assert r.status_code == 200, r.text
    S["subject"] = r.json()["id"]

    # Мугалимдерди Excel менен жүктөө (ТЗдагы дарек)
    r = client.post("/admin/excel/import-teachers", headers=h, files={
        "file": ("teachers.xlsx", excel([
            ["90000000000010", "Класс Жетекчи Мугалим", "+996700000010"],
            ["90000000000011", "Башка Мугалим", None],
            ["123", "Ката ИНН", None],
        ]), XLSX)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_added"] == 2 and body["total_errors"] == 1
    teacher_pw = {t["inn"]: t["temporary_password"] for t in body["added_teachers"]}

    # Завуч мугалимдердин убактылуу сыр сөздөрүн кийин да ала алат
    r = client.get("/admin/teachers/temp-passwords", headers=h)
    listed = {t["inn"]: t for t in r.json()["teachers"]}
    assert listed["90000000000010"]["temporary_password"] == teacher_pw["90000000000010"]
    S["teacher_id"] = listed["90000000000010"]["id"]
    S["teacher2_id"] = listed["90000000000011"]["id"]

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

    S["teacher"] = login_and_change(client, "90000000000010", teacher_pw["90000000000010"])
    S["teacher2"] = login_and_change(client, "90000000000011", teacher_pw["90000000000011"])

    # Сыр сөз алмашкандан кийин убактылуу сыр сөз базадан өчөт
    r = client.get("/admin/teachers/temp-passwords", headers=h)
    listed = {t["inn"]: t for t in r.json()["teachers"]}
    assert listed["90000000000010"]["temporary_password"] is None


def test_import_students_and_temp_passwords(client):
    h = auth(S["director"])

    r = client.get("/admin/excel/templates/students", headers=h)
    assert r.status_code == 200 and r.content[:2] == b"PK"

    r = client.post("/admin/excel/import-students", headers=h,
                    data={"class_id": str(S["class"])},
                    files={"file": ("students.xlsx", excel([
                        ["90000000000101", "Алиев Эркин", "+996700000101"],
                        ["90000000000102", "Токтосунов Бекзат", None],
                        ["90000000000103", "Жумабекова Айдана", None],
                    ]), XLSX)})
    assert r.status_code == 200, r.text
    assert r.json()["total_added"] == 3

    # Класс жетекчи өз классынын логин/сыр сөздөрүн алат
    r = client.get(f"/classes/{S['class']}/temp-passwords", headers=auth(S["teacher"]))
    assert r.status_code == 200, r.text
    students = r.json()["students"]
    assert len(students) == 3 and all(s["temporary_password"] for s in students)
    S["students"] = {s["inn"]: s for s in students}

    r = client.get(f"/classes/{S['class']}/temp-passwords?format=xlsx", headers=auth(S["teacher"]))
    assert r.status_code == 200 and r.content[:2] == b"PK"

    # Башка мугалим көрө албайт
    r = client.get(f"/classes/{S['class']}/temp-passwords", headers=auth(S["teacher2"]))
    assert r.status_code == 403

    # Башка мектептин директору бул классты таптакыр көрбөйт (multi-tenant)
    r = client.get(f"/classes/{S['class']}/temp-passwords", headers=auth(S["other_director"]))
    assert r.status_code == 404


def test_parent_and_student_accounts(client):
    erkin = S["students"]["90000000000101"]
    bekzat = S["students"]["90000000000102"]

    r = client.post("/parents/register", json={
        "inn": "90000000000201", "full_name": "Асанова Назира", "password": "Parent#2026",
        "student_inn": erkin["inn"], "student_password": erkin["temporary_password"]})
    assert r.status_code == 200, r.text
    S["parent"] = r.json()["access_token"]

    r = client.post("/parents/add-child", headers=auth(S["parent"]), json={
        "student_inn": bekzat["inn"], "student_password": bekzat["temporary_password"]})
    assert r.status_code == 200, r.text

    S["erkin_id"], S["bekzat_id"] = erkin["id"], bekzat["id"]
    S["aidana_id"] = S["students"]["90000000000103"]["id"]
    S["erkin"] = login_and_change(client, erkin["inn"], erkin["temporary_password"])

    r = client.get("/me", headers=auth(S["parent"]))
    assert r.status_code == 200 and len(r.json()["children"]) == 2
    assert r.json()["children"][0]["class_name"] == "11-А"


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
    login(client, "90000000000101", "Another#2026")

    # Класс жетекчи окуучунун сыр сөзүн баштапкы абалга келтирет
    r = client.post(f"/classes/{S['class']}/students/{S['erkin_id']}/reset-password",
                    headers=auth(S["teacher"]))
    assert r.status_code == 200
    assert login(client, "90000000000101", r.json()["temporary_password"])["requires_password_change"]

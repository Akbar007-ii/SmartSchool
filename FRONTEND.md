# Smart School API — фронтенд үчүн колдонмо

- **Base URL:** `http://<СЕРВЕРДИН-IP>` (бэкендчиден алыңыз)
- **Swagger (бардык эндпоинттер, схемалар, түз сыноо):** `http://<СЕРВЕРДИН-IP>/docs`
- **Postman коллекциясы:** [`postman/SmartSchool.postman_collection.json`](postman/SmartSchool.postman_collection.json) — 171 даяр суроо
- **OpenAPI JSON** (TypeScript типтерин генерациялоо үчүн): `http://<СЕРВЕРДИН-IP>/openapi.json`
  ```bash
  npx openapi-typescript http://<IP>/openapi.json -o src/api/schema.d.ts
  ```

## Демо аккаунттар

Сыр сөз бардыгында: **`Demo#2026`**

| Ролу | ИНН (логин) | Аты-жөнү | Эскертүү |
|---|---|---|---|
| DIRECTOR | `10000000000001` | Асанов Бакыт | Админ-панель |
| TEACHER | `10000000000010` | Иванова Мария Петровна | 11-А класс жетекчи, Кыргыз тили |
| TEACHER | `10000000000011` | Сапарова Гүлнара | 11-Б класс жетекчи, Математика, Физика |
| STUDENT | `10000000000101` | Алиев Эркин | 11-А |
| STUDENT | `10000000000102`…`106` | 5 окуучу | 11-А, 11-Б |
| PARENT | `10000000000201` | Алиева Назира | Эркин менен Айдананын ата-энеси |

## Авторизация

```http
POST /auth/login
{"inn": "10000000000101", "password": "Demo#2026"}

→ {"access_token": "eyJ...", "token_type": "bearer", "requires_password_change": false}
```

Андан кийинки бардык суроолордо: `Authorization: Bearer <access_token>`.
Токен 12 саат жарактуу; `401` келсе — логин барагына кайтарыңыз.

**Биринчи кирүү:** `requires_password_change: true` болсо, колдонуучуну сыр сөз алмаштыруу
барагына жибериңиз:

```http
POST /auth/first-login-change
{"current_password": "<убактылуу>", "new_password": "<кеминде 8 белги>"}
→ жаңы access_token кайтат, ошону сактаңыз
```

Кирген соң ролду жана кабинеттин маалыматын `GET /me` берет: `role`, `school`, ошондой эле
окуучуда `student` (XP, орундар, значоктор), ата-энеде `children`, мугалимде `classes_led`,
`is_class_teacher`, `assignments`.

## Ролдор жана кабинеттер

| `role` | Кабинет |
|---|---|
| `DIRECTOR`, `DEPUTY` | Админ-панель: мектеп, класстар, мугалимдер, Excel, бекитүүлөр, сыр сөздөр, олимпиада, жарыялар |
| `TEACHER`, `CLASS_TEACHER` | Журнал, үй тапшырма. `GET /me` ичинде `is_class_teacher: true` болсо — суранууларды кароо жана класстын сыр сөздөрү |
| `STUDENT` | Күндөлүк, үй тапшырма, рейтинг, профиль. **Сурануу баракчасы жок** |
| `PARENT` | Баланын баалары, үй тапшырмалары, **сабактан сурануу** |

> Класс жетекчи ролу менен эмес, класска байланыш менен аныкталат — `is_class_teacher` колдонуңуз.

## Каталар

Ката болгондо: `{"detail": "Кыргызча билдирүү"}` — `detail`'ди колдонуучуга түз көрсөтсө болот.
Форманын валидация катасы (`422`) болсо `detail` — тизме: `[{"loc": [...], "msg": "..."}]`.

| Код | Мааниси |
|---|---|
| 401 | Токен жок/мөөнөтү бүттү → логинге |
| 403 | Бул ролго уруксат жок |
| 404 | Табылган жок (же башка мектептики) |
| 409 | Кайталанма (мис. ошол күнгө сурануу бар) |

## Маалымат форматтары

- Даталар: `YYYY-MM-DD`. Убакыт: ISO 8601, Бишкек убактысы (`+06:00`).
- Файлдар (сүрөт, PDF, аватар, баннер) салыштырмалуу дарек менен келет: `"/media/homeworks/1/abc.png"`
  → толук дарек: `BASE_URL + url`.
- Катышуу (`attendance`): `Б` — бар, `Ж` — себепсиз жок, `К` — кечикти, `С` — себептүү (сурануу бекитилген).
- Баа (`grade_value`): `2`–`5` же `null`.
- Значоктор (`badge_type` → `icon_name`): `SUBJECT_LEADER` → `crown` (алтын таажы),
  `PARALLEL_CHAMP` → `medal`, `PERFECT_ATTENDANCE` → `lightning`, `OLYMPIAD_CANDIDATE` → `star`.

## Файл жүктөө (multipart/form-data)

`fetch` менен `FormData` колдонуңуз, `Content-Type` баш сабын **өзүңүз койбоңуз** (браузер коёт):

```js
const form = new FormData();
form.append("assignment_id", 1);
form.append("title", "№234, 235, 236 көнүгүүлөр");
files.forEach(f => form.append("files", f));      // бир нече файл — бир эле ачкыч менен
await fetch(`${BASE_URL}/homeworks`, {method: "POST", headers: {Authorization: `Bearer ${token}`}, body: form});
```

Чектөөлөр: бир файл 10 MB чейин, бир жолу 10 файлга чейин; jpg/png/webp/heic, pdf, doc(x), ppt(x), xls(x), txt.

## Экрандар → эндпоинттер

### Ачык барактар (токенсиз)
| Экран | Эндпоинт |
|---|---|
| Башкы бет (12 мектеп · 25 000+ окуучу) | `GET /public/stats` |
| Мектеп тандоо (издөө) | `GET /public/schools?search=` |
| Мектептин баракчасы | `GET /public/schools/{id}` |

### Окуучу
| Экран | Эндпоинт |
|---|---|
| Башкы панель: карточкалар | `GET /dashboard/stats` |
| Башкы панель: орду, XP, значоктор | `GET /ratings/me` |
| Күндөлүк | `GET /journal/diary?date_from=&date_to=` |
| Үй тапшырмалар | `GET /homeworks`, `GET /homeworks/{id}` |
| Тапшырманы тапшыруу | `POST /homeworks/{id}/submit` (form: `text`, `files`) |
| Рейтинг: класс / параллель / предмет / мектеп | `GET /ratings/class/{class_id}`, `/ratings/parallel/{grade}`, `/ratings/subjects/{id}`, `/ratings/school` |
| Профиль | `GET /me`, `PUT /me`, `POST /me/avatar`, `POST /me/change-password` |
| Жарыялар | `GET /announcements` |
| 🔔 Билдирүүлөр | `GET /notifications/unread-count`, `GET /notifications`, `POST /notifications/{id}/read`, `POST /notifications/read-all` |

### Ата-эне
Окуучунун эндпоинттери менен бирдей, бирок `?student_id=<бала>` кошулат
(балдарынын тизмеси — `GET /me` → `children`). Мисалы: `GET /journal/diary?student_id=5`,
`GET /homeworks?student_id=5`, `GET /ratings/me?student_id=5`.

| Экран | Эндпоинт |
|---|---|
| Баланын жыйынтыгы, өсүү темпи | `GET /journal/summary?student_id=` (`subjects[].trend` — айлык орточо) |
| Баланын профили | `GET /profiles/students/{id}` |
| **Сабактан сурануу** | см. төмөн |

### Сабактан сурануу (ата-эне гана)

1. Баракча ачылганда `GET /absence-requests/status`:
   `{"is_open_for_today": true, "deadline": "08:00", "can_submit": true}`.
   `is_open_for_today: false` болсо — «бүгүнкү күнгө» баскычын өчүрүңүз (эртеңки күнгө жибере берет).
2. Жөнөтүү: `POST /absence-requests`
   ```json
   {"student_id": 5, "target_date": "2026-11-13", "reason": "Оору", "comment": "Температурасы бар"}
   ```
   `target_date` берилбесе — бүгүн. 08:00дөн кийин бүгүнкү күнгө `403`, кайталанса `409`.
3. Тизме: `GET /absence-requests` (статустары `PENDING`, `APPROVED`, `REJECTED`, `CANCELLED`).
4. Жокко чыгаруу: `POST /absence-requests/{id}/cancel` (PENDING гана).

Окуучу бул эндпоинттердин баарынан `403` алат — окуучуга сурануу менюсун көрсөтпөңүз.

### Мугалим
| Экран | Эндпоинт |
|---|---|
| Менин журналдарым (класс + предмет) | `GET /journal/assignments` (`can_edit`) |
| Журнал — бир сабак, бир күн | `GET /journal?assignment_id=&day=YYYY-MM-DD` |
| Баа/катышуу сактоо | `PUT /journal` `{"assignment_id", "date", "entries": [{"student_id", "grade_value", "attendance", "comment"}]}` |
| Үй тапшырма түзүү | `POST /homeworks` (form) · өзгөртүү `PUT /homeworks/{id}` · файл `POST/DELETE /homeworks/{id}/files` |
| Тапшырылган иштер | `GET /homeworks/{id}/submissions` |
| Олимпиадага сунуштоо | `POST /olympiad/candidates` |

`excused: true` болгон окуучуга баа коюлбайт (сурануусу бекитилген, катышуу автоматтык `С`).

### Класс жетекчи (кошумча)
| Экран | Эндпоинт |
|---|---|
| Суранууларым | `GET /absence-requests?status=PENDING` |
| Уруксат берүү / Четке кагуу | `POST /absence-requests/{id}/approve`, `.../reject` `{"comment": "..."}` |
| Класстын бир күнү | `GET /journal/class/{class_id}?day=` |
| Окуучулардын логин/сыр сөздөрү | `GET /classes/{id}/temp-passwords` (`?format=xlsx` — Excel файл) |
| Окуучунун сыр сөзүн жаңыртуу | `POST /classes/{id}/students/{sid}/reset-password` |

### Директор / Завуч (админ-панель)
| Экран | Эндпоинт |
|---|---|
| Мектептин баракчасы | `GET/PUT /schools/me`, `POST /schools/me/banner`, `POST /schools/me/logo` |
| Класстар | `GET/POST /classes/`, `PUT/DELETE /classes/{id}`, `PUT /classes/{id}/class-teacher` |
| Предметтер | `GET/POST /subjects/` |
| Excel үлгүлөрү | `GET /admin/excel/templates/students`, `.../teachers` |
| Окуучуларды Excel менен жүктөө | `POST /admin/excel/import-students` (form: `class_id`, `file`) |
| Мугалимдерди Excel менен жүктөө | `POST /admin/excel/import-teachers` (form: `file`) |
| Бирден кошуу | `POST /students/`, `POST /users/create-teacher` |
| Мугалимдер жана байлоо | `POST /admin/teacher-assignments`, `GET /teacher-assignments/`, `DELETE /teacher-assignments/{id}` |
| Мугалимдердин сыр сөздөрү | `GET /admin/teachers/temp-passwords` (`?format=xlsx`), `POST /admin/users/{id}/reset-password` |
| Суранууларды көзөмөлдөө | `GET /absence-requests` (көрүү гана) |
| Журналды көрүү | `GET /journal/assignments`, `GET /journal?...` (`can_edit: false`) |
| Олимпиадалык аналитика | `GET /olympiad/analytics`, `POST /olympiad/auto-select`, `POST /olympiad/candidates/{id}/approve` |
| Жарыялар | `POST/PUT/DELETE /announcements` (form: `title`, `body`, `event_date`, `image`) |
| Кийинки окуу жылына өткөрүү | `GET /students/promotion/preview`, `POST /students/promotion/execute` |

Excel файл кайтарган эндпоинттерди (`?format=xlsx`, үлгүлөр) `fetch` → `blob()` менен жүктөп алыңыз.

# Smart School API — AWS'ке жайгаштыруу (Docker, MVP)

Натыйжа: API `http://<СЕРВЕРДИН-IP>` дарегинде иштейт, Swagger документациясы — `http://<СЕРВЕРДИН-IP>/docs`.
Домен жана HTTPS бул этапта жок (MVP).

## 1. EC2 сервер түзүү

AWS Console → **EC2 → Launch instance**:

| Параметр | Маани |
|---|---|
| AMI | Ubuntu Server 24.04 LTS |
| Instance type | `t3.small` (2 GB RAM). `t3.micro` (1 GB) иштейт, бирок PostgreSQL + bcrypt менен тар |
| Key pair | Жаңы ачкыч түзүп, `.pem` файлын сактап коюңуз |
| Storage | 20 GB gp3 |
| Security group | **SSH (22)** — My IP гана; **HTTP (80)** — Anywhere (0.0.0.0/0) |

Түзүлгөндөн кийин **Elastic IP** бөлүп, ушул серверге байлаңыз — антпесе сервер кайра
күйгөндө IP дарек алмашып, фронтенддеги дарек иштебей калат.

> 5432 (PostgreSQL) портун Security group'та АЧПАҢЫЗ. База Docker ичинде гана жеткиликтүү.

## 2. Серверге кирүү жана Docker орнотуу

```bash
ssh -i smartschool.pem ubuntu@<СЕРВЕРДИН-IP>

curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
exit   # кайра кириңиз, docker тобу күчүнө кирет
```

## 3. Долбоорду жүктөө жана жөндөө

```bash
git clone https://github.com/Akbar007-ii/SmartSchool.git
cd SmartSchool
cp .env.example .env
```

`.env` файлын толтуруңуз (`nano .env`):

```bash
# Ачкычтарды түзүү:
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # -> SECRET_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(24))"   # -> DB_PASSWORD
```

| Өзгөрмө | Эмне жазылат |
|---|---|
| `SECRET_KEY` | Жогорудагы биринчи буйрук берген сап. **Кийин алмаштырбаңыз** — бардык токендер жана сакталган убактылуу сыр сөздөр жараксыз болот |
| `DB_PASSWORD` | Экинчи буйрук берген сап (жергиликтүү компьютердегиден башка болсун) |
| `CORS_ORIGINS` | MVP үчүн `*`. Фронтенддин дареги белгилүү болгондо ошону жазыңыз |
| `API_PORT` | `80` |

## 4. Иштетүү

```bash
docker compose up -d --build
docker compose ps            # api жана db "healthy" болушу керек
curl http://localhost/health # {"status":"ok"}
```

API ар бир ишке киргенде миграцияларды (`alembic upgrade head`) өзү колдонот.

## 5. Биринчи маалыматтар

Фронтенд иштеп чыгуу үчүн демо-мектеп (бардык ролдор, журнал, рейтинг, үй тапшырма, сурануу):

```bash
docker compose exec api python seed_demo.py
```

Чыныгы мектеп кошуу (директор биринчи киргенде сыр сөзүн алмаштырат):

```bash
docker compose exec api python create_admin.py --school "№1 Мектеп" --inn 01234567890123 --name "Асанов Асан" --address "Бишкек"
```

Калган баарын (класстар, мугалимдер, окуучулар Excel менен) директор API/сайт аркылуу кошот.

## 6. Жаңыртуу

```bash
cd SmartSchool
git pull
docker compose up -d --build
```

## 7. Резервдик көчүрмө

```bash
# База
docker compose exec -T db pg_dump -U postgres school | gzip > backup_$(date +%F).sql.gz

# Жүктөлгөн файлдар (сүрөт, PDF)
docker run --rm -v smartschool_media:/m -v "$PWD":/b alpine tar czf /b/media_$(date +%F).tar.gz -C /m .

# Калыбына келтирүү
gunzip -c backup_2026-11-12.sql.gz | docker compose exec -T db psql -U postgres school
```

(Volume'дун так аты: `docker volume ls` — папканын атына жараша `smartschool_media` же башкача болушу мүмкүн.)

## 8. Пайдалуу буйруктар

```bash
docker compose logs -f api     # API логдору
docker compose restart api     # API'ни кайра иштетүү
docker compose down            # Токтотуу (маалымат volume'дарда сакталат)
```

> `docker compose down -v` маалыматтар базасын жана жүктөлгөн файлдарды **биротоло өчүрөт**.

## Белгилүү чектөөлөр (MVP)

- **HTTPS жок.** Эгер фронтенд HTTPS дарекке (мис. Vercel) жайгаштырылса, браузер `http://` API'ге
  суроону бөгөттөйт (mixed content). Ал учурда API'ге домен + SSL керек — бул кийинки кадам.
  Фронтчу `http://localhost:3000` дарегинен иштеп чыкканда эч кандай көйгөй жок.
- Кирүү эндпоинтинде аракеттердин санын чектөө (rate limit) жок.
- Жүктөлгөн файлдар сервердин дискинде сакталат (бир сервер үчүн жетиштүү).

"""Postman тесттери үчүн ӨЗҮНЧӨ таза база даярдайт (негизги базага тийбейт).

    python postman/seed_test_db.py

`school_postman` базасын өчүрүп кайра түзөт, таблицаларды курат жана эки мектеп
менен эки директорду кошот. Андан кийин серверди ошол базага каршы иштетиңиз:

    DB_NAME=school_postman uvicorn main:app --port 8010
"""
import os
import sys
from pathlib import Path

TEST_DB = "school_postman"
os.environ["DB_NAME"] = TEST_DB
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text  # noqa: E402

from mysite.db.database import DATABASE_URL, SessionLocal, engine  # noqa: E402
from mysite.db.models import Base, Schools, Users  # noqa: E402
from mysite.security.hashing import hash_password  # noqa: E402

assert DATABASE_URL.database == TEST_DB, "Коопсуздук: тест базасы гана колдонулат"

admin_engine = create_engine(DATABASE_URL.set(database="postgres"), isolation_level="AUTOCOMMIT")
with admin_engine.connect() as connection:
    connection.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)'))
    connection.execute(text(f'CREATE DATABASE "{TEST_DB}"'))
admin_engine.dispose()

Base.metadata.create_all(engine)

db = SessionLocal()
school = Schools(name="Postman тест мектеби №1", address="Бишкек шаары")
other = Schools(name="Postman тест мектеби №2", address="Ош шаары")
db.add_all([school, other])
db.flush()
db.add_all([
    Users(inn="90000000000001", full_name="Тест Директор", role="DIRECTOR",
          hashed_password=hash_password("Mektep#2026"), school_id=school.id,
          is_temp_password=True),
    Users(inn="90000000000002", full_name="Башка Директор", role="DIRECTOR",
          hashed_password=hash_password("Mektep#2026"), school_id=other.id,
          is_temp_password=False),
])
db.commit()
db.close()
print(f"'{TEST_DB}' базасы даяр. Директор: 90000000000001 / Mektep#2026")

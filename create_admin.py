
from mysite.db.database import SessionLocal
from mysite.db.models import Schools, Users
from mysite.security.hashing import hash_password

db = SessionLocal()

try:
    # 1. Мектеп түзүү
    school = Schools(
        name="Smart School №1",
        address="Бишкек шаары",
        phone="+996700000000",
        director_name="Тесттик директор"
    )

    db.add(school)
    db.flush()

    # 2. Директор түзүү
    director = Users(
        inn="01234567890123",
        full_name="Тесттик Директор",
        role="DIRECTOR",
        hashed_password=hash_password("Mektep#2026"),
        school_id=school.id,
        is_temp_password=True
    )

    db.add(director)
    db.commit()

    print("SCHOOL CREATED:", school.id)
    print("DIRECTOR CREATED:", director.id)
    print("LOGIN:", director.inn)
    print("PASSWORD: Mektep#2026")

except Exception as e:
    db.rollback()
    print("ERROR:", e)

finally:
    db.close()

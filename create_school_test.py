
from mysite.db.database import SessionLocal
from mysite.db.models import Schools, Users
from mysite.security.hashing import hash_password

db = SessionLocal()

try:
    school = Schools(
        name="Test School 2",
        address="Bishkek"
    )

    db.add(school)
    db.commit()
    db.refresh(school)

    print("SCHOOL 2 CREATED:", school.id)

    user = Users(
        inn="12345678901234",
        full_name="Second Director",
        role="DIRECTOR",
        hashed_password=hash_password("School2#2026"),
        school_id=school.id,
        is_temp_password=True,
        is_active=True
    )

    db.add(user)
    db.commit()

    print("DIRECTOR 2 CREATED")

finally:
    db.close()

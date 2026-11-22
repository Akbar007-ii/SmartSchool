"""Платформанын администраторун (SYSTEM_ADMIN) түзөт — бардык мектептердин үстүндө.

Колдонуу:
    python create_system_admin.py --email admin@gmail.com --name "Асанов Асан"

Docker'де:
    docker compose exec api python create_system_admin.py --email admin@gmail.com --name "Асанов Асан"

Убактылуу сыр сөз экранга чыгат; биринчи киргенде аны алмаштыруу талап кылынат.
Андан кийин мектептерди жана алардын директорлорун API аркылуу кошот: POST /system/schools
"""
import argparse
import sys

from mysite.db.database import SessionLocal
from mysite.db.models import Users
from mysite.db.schema import normalize_email
from mysite.services.passwords import set_temp_password

parser = argparse.ArgumentParser(description="Платформанын администраторун түзүү")
parser.add_argument("--email", required=True, help="Почта (логин)")
parser.add_argument("--name", required=True, help="Аты-жөнү")
args = parser.parse_args()

try:
    email = normalize_email(args.email)
except ValueError as error:
    sys.exit(f"КАТА: {error}")

db = SessionLocal()

try:
    if db.query(Users).filter(Users.email == email).first():
        sys.exit("КАТА: бул почта мурда катталган")

    admin = Users(
        email=email,
        full_name=args.name,
        role="SYSTEM_ADMIN",
        hashed_password="",
        school_id=None,
    )
    password = set_temp_password(admin)
    db.add(admin)
    db.commit()

    print("Платформанын администратору түзүлдү: id =", admin.id, "|", admin.full_name)
    print("Логин (почта):      ", admin.email)
    print("Убактылуу сыр сөз:  ", password)

except Exception as error:
    db.rollback()
    sys.exit(f"КАТА: {error}")

finally:
    db.close()

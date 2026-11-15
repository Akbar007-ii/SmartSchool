"""Платформанын администраторун (SYSTEM_ADMIN) түзөт — бардык мектептердин үстүндө.

Колдонуу:
    python create_system_admin.py --inn 01234567890123 --name "Асанов Асан"

Docker'де:
    docker compose exec api python create_system_admin.py --inn 01234567890123 --name "Асанов Асан"

Убактылуу сыр сөз экранга чыгат; биринчи киргенде аны алмаштыруу талап кылынат.
Андан кийин мектептерди жана алардын директорлорун API аркылуу кошот: POST /system/schools
"""
import argparse
import sys

from mysite.db.database import SessionLocal
from mysite.db.models import Users
from mysite.services.passwords import set_temp_password

parser = argparse.ArgumentParser(description="Платформанын администраторун түзүү")
parser.add_argument("--inn", required=True, help="14 орундуу ИНН (логин)")
parser.add_argument("--name", required=True, help="Аты-жөнү")
parser.add_argument("--phone", default=None, help="Телефон")
args = parser.parse_args()

if not args.inn.isdigit() or len(args.inn) != 14:
    sys.exit("КАТА: ИНН 14 цифрадан турушу керек")

db = SessionLocal()

try:
    if db.query(Users).filter(Users.inn == args.inn).first():
        sys.exit("КАТА: бул ИНН мурда катталган")

    admin = Users(
        inn=args.inn,
        full_name=args.name,
        phone=args.phone,
        role="SYSTEM_ADMIN",
        hashed_password="",
        school_id=None,
    )
    password = set_temp_password(admin)
    db.add(admin)
    db.commit()

    print("Платформанын администратору түзүлдү: id =", admin.id, "|", admin.full_name)
    print("Логин (ИНН):        ", admin.inn)
    print("Убактылуу сыр сөз:  ", password)

except Exception as error:
    db.rollback()
    sys.exit(f"КАТА: {error}")

finally:
    db.close()

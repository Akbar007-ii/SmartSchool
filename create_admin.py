"""Жаңы мектепти жана анын директорун түзөт.

Колдонуу:
    python create_admin.py --school "№1 Мектеп" --inn 01234567890123 --name "Асанов Асан"

Docker'де:
    docker compose exec api python create_admin.py --school "№1 Мектеп" --inn 01234567890123 --name "Асанов Асан"

Сыр сөз берилбесе, убактылуу сыр сөз автоматтык түзүлүп экранга чыгат.
Директор биринчи киргенде аны алмаштырууга милдеттүү.
"""
import argparse
import sys

from mysite.db.database import SessionLocal
from mysite.db.models import Schools, Users
from mysite.services.passwords import set_temp_password

parser = argparse.ArgumentParser(description="Мектеп жана директор түзүү")
parser.add_argument("--school", required=True, help="Мектептин аты")
parser.add_argument("--inn", required=True, help="Директордун 14 орундуу ИНН номери")
parser.add_argument("--name", required=True, help="Директордун аты-жөнү")
parser.add_argument("--address", default=None, help="Мектептин дареги")
parser.add_argument("--phone", default=None, help="Мектептин телефону")
parser.add_argument("--password", default=None, help="Убактылуу сыр сөз (берилбесе автоматтык түзүлөт)")
args = parser.parse_args()

if not args.inn.isdigit() or len(args.inn) != 14:
    sys.exit("КАТА: ИНН 14 цифрадан турушу керек")

if args.password is not None and len(args.password) < 8:
    sys.exit("КАТА: сыр сөз кеминде 8 белгиден турушу керек")

db = SessionLocal()

try:
    if db.query(Users).filter(Users.inn == args.inn).first():
        sys.exit("КАТА: бул ИНН мурда катталган")

    school = Schools(
        name=args.school,
        address=args.address,
        phone=args.phone,
        director_name=args.name,
    )
    db.add(school)
    db.flush()

    director = Users(
        inn=args.inn,
        full_name=args.name,
        role="DIRECTOR",
        hashed_password="",
        school_id=school.id,
    )
    password = set_temp_password(director, args.password)
    db.add(director)
    db.commit()

    print("Мектеп түзүлдү:  id =", school.id, "|", school.name)
    print("Директор түзүлдү: id =", director.id, "|", director.full_name)
    print("Логин (ИНН):          ", director.inn)
    print("Убактылуу сыр сөз:    ", password)

except Exception as error:
    db.rollback()
    sys.exit(f"КАТА: {error}")

finally:
    db.close()

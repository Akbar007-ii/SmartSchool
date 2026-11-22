"""Жаңы мектепти жана анын директорун түзөт.

Колдонуу:
    python create_admin.py --school "№1 Мектеп" --email director@gmail.com --name "Асанов Асан"

Docker'де:
    docker compose exec api python create_admin.py --school "№1 Мектеп" --email director@gmail.com --name "Асанов Асан"

Сыр сөз берилбесе, убактылуу сыр сөз автоматтык түзүлүп экранга чыгат.
Директор биринчи киргенде аны алмаштырууга милдеттүү.
"""
import argparse
import sys

from mysite.db.database import SessionLocal
from mysite.db.models import Schools, Users
from mysite.db.schema import normalize_email
from mysite.services.passwords import set_temp_password

parser = argparse.ArgumentParser(description="Мектеп жана директор түзүү")
parser.add_argument("--school", required=True, help="Мектептин аты")
parser.add_argument("--email", required=True, help="Директордун почтасы (логин)")
parser.add_argument("--name", required=True, help="Директордун аты-жөнү")
parser.add_argument("--password", default=None, help="Убактылуу сыр сөз (берилбесе автоматтык түзүлөт)")
args = parser.parse_args()

try:
    email = normalize_email(args.email)
except ValueError as error:
    sys.exit(f"КАТА: {error}")

if args.password is not None and len(args.password) < 8:
    sys.exit("КАТА: сыр сөз кеминде 8 белгиден турушу керек")

db = SessionLocal()

try:
    if db.query(Users).filter(Users.email == email).first():
        sys.exit("КАТА: бул почта мурда катталган")

    school = Schools(
        name=args.school,
        director_name=args.name,
    )
    db.add(school)
    db.flush()

    director = Users(
        email=email,
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
    print("Логин (почта):        ", director.email)
    print("Убактылуу сыр сөз:    ", password)

except Exception as error:
    db.rollback()
    sys.exit(f"КАТА: {error}")

finally:
    db.close()

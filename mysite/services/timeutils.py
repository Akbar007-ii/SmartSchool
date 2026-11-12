"""Сервердик убакыт: бардык эрежелер Бишкек убактысы (UTC+6) боюнча текшерилет."""
from datetime import date, datetime, time, timedelta, timezone

# Кыргызстанда жайкы/кышкы убакыт которулбайт — туруктуу UTC+6.
BISHKEK_TZ = timezone(timedelta(hours=6), name="Asia/Bishkek")

# Сабактан сурануу ушул убакытка чейин гана кабыл алынат.
ABSENCE_DEADLINE = time(8, 0)

# Канча күн алдын ала сурануу жиберүүгө болот.
ABSENCE_MAX_DAYS_AHEAD = 14


def now_local() -> datetime:
    return datetime.now(BISHKEK_TZ)


def today_local() -> date:
    return now_local().date()


def current_academic_year(today: date | None = None) -> str:
    """Окуу жылы 1-сентябрдан башталат: 2026-10-01 -> '2026-2027'."""
    today = today or today_local()
    start = today.year if today.month >= 9 else today.year - 1
    return f"{start}-{start + 1}"

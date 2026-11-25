"""Күнүнө бир жолу: окулбаган билдирүүлөрдүн жыйынтыгын почтага жөнөтөт.

Ар бир окуя үчүн өзүнчө кат жиберилсе, ата-эне күнүнө ондогон кат алмак.
Ошондуктан акыркы 24 сааттагы окулбаган билдирүүлөр бир катка чогултулат.
Профилинде «Почтага билдирүүлөр» өчүрүлгөн колдонуучуларга кат жөнөтүлбөйт.

Серверде cron аркылуу иштетилет (deploy/crontab.example):
    docker compose exec -T api python send_daily_digest.py
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from mysite.db.database import SessionLocal
from mysite.db.models import Notifications, Users
from mysite.services.mailer import FRONTEND_URL, is_configured, send_email_now

# Каттарда эң көп ушунча билдирүү көрсөтүлөт, калганы — «дагы N»
MAX_ITEMS_IN_EMAIL = 15

db = SessionLocal()
try:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    rows = (
        db.query(Users.email, Users.full_name, Notifications.title)
        .join(Notifications, Notifications.user_id == Users.id)
        .filter(
            Notifications.is_read.is_(False),
            Notifications.created_at >= since,
            Users.is_active.is_(True),
            Users.email_notifications.is_(True),
        )
        .order_by(Users.id, Notifications.created_at)
        .all()
    )

    titles_by_user = defaultdict(list)
    names = {}
    for email, full_name, title in rows:
        titles_by_user[email].append(title)
        names[email] = full_name

    for email, titles in titles_by_user.items():
        lines = [f"• {title}" for title in titles[:MAX_ITEMS_IN_EMAIL]]
        if len(titles) > MAX_ITEMS_IN_EMAIL:
            lines.append(f"…жана дагы {len(titles) - MAX_ITEMS_IN_EMAIL}")
        send_email_now(
            email,
            f"Smart School: бүгүн {len(titles)} жаңылык",
            f"Саламатсызбы, {names[email]}!\n\n"
            "Акыркы суткада:\n" + "\n".join(lines) + "\n\n"
            f"Толугу менен: {FRONTEND_URL}\n\n"
            "Бул каттарды профилиңизден өчүрө аласыз.",
        )

    print(f"Жыйынтык жөнөтүлдү: {len(titles_by_user)} колдонуучу"
          + ("" if is_configured() else " (SMTP жок — каттар логго гана жазылды)"))
finally:
    db.close()

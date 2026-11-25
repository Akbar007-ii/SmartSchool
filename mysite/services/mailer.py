"""Электрондук каттарды жөнөтүү (SMTP).

Жөндөөлөр .env файлынан: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM.
SMTP_HOST жок болсо, кат жөнөтүлбөйт — анын мазмуну логго гана жазылат
(иштеп чыгуу жана тест учурунда ыңгайлуу).

Кат өзүнчө агымда (thread) жөнөтүлөт: суроо SMTP серверин күтпөйт.
"""
import logging
import os
import smtplib
import threading
from email.message import EmailMessage

logger = logging.getLogger("smartschool.mail")

# Каттагы шилтемелер ушул дарекке жетелейт (мисалы, https://smart-school-sable.vercel.app)
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")

# Орун басар почталарга (миграция берген user<id>@smartschool.local) кат жөнөтүлбөйт
PLACEHOLDER_DOMAINS = ("smartschool.local",)


def is_configured() -> bool:
    return bool(os.getenv("SMTP_HOST"))


def _send(to: str, subject: str, text: str) -> None:
    host = os.getenv("SMTP_HOST")
    if not host:
        logger.warning("SMTP жөндөлгөн эмес. Кат жөнөтүлгөн жок: %s | %s\n%s", to, subject, text)
        return

    message = EmailMessage()
    message["From"] = os.getenv("SMTP_FROM") or os.getenv("SMTP_USER", "")
    message["To"] = to
    message["Subject"] = subject
    message.set_content(text)

    try:
        with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=20) as smtp:
            smtp.starttls()
            user = os.getenv("SMTP_USER")
            if user:
                smtp.login(user, os.getenv("SMTP_PASSWORD", ""))
            smtp.send_message(message)
    except Exception:
        # Кат жетпей калса да негизги аракет (баа, тапшырма) бузулбашы керек
        logger.exception("Кат жөнөтүлгөн жок: %s", to)


def send_email_now(to: str, subject: str, text: str) -> None:
    """Катты ушул эле агымда жөнөтөт (скрипттер үчүн, мисалы send_daily_digest.py)."""
    if to and not to.endswith(PLACEHOLDER_DOMAINS):
        _send(to, subject, text)


def send_email(to: str, subject: str, text: str) -> None:
    """Катты фондо жөнөтөт; орун басар почталарды өткөрүп жиберет."""
    if not to or to.endswith(PLACEHOLDER_DOMAINS):
        return
    threading.Thread(target=_send, args=(to, subject, text), daemon=True).start()

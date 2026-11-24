from typing import Iterable, Optional

from sqlalchemy.orm import Session

from mysite.db.models import Notifications, Users
from mysite.services.mailer import FRONTEND_URL, send_email


def notify(
    db: Session,
    user_ids: int | Iterable[int],
    title: str,
    body: Optional[str] = None,
    link: Optional[str] = None,
) -> None:
    """Билдирүү түзөт (commit кылбайт — чакыруучу транзакцияга кошулат)."""
    if isinstance(user_ids, int):
        user_ids = [user_ids]
    user_ids = {user_id for user_id in user_ids if user_id is not None}
    for user_id in user_ids:
        db.add(Notifications(user_id=user_id, title=title, body=body, link=link))

    # Профилинде каттарды өчүрбөгөндөргө почтага көчүрмө жөнөтүлөт
    recipients = db.query(Users.email).filter(
        Users.id.in_(user_ids),
        Users.is_active.is_(True),
        Users.email_notifications.is_(True),
    ).all() if user_ids else []
    text = "\n\n".join(part for part in (
        body,
        f"{FRONTEND_URL}{link}" if link else FRONTEND_URL,
        "Smart School. Каттарды профилиңизден өчүрө аласыз.",
    ) if part)
    for (email,) in recipients:
        send_email(email, f"Smart School: {title}", text)

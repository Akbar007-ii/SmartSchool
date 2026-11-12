from typing import Iterable, Optional

from sqlalchemy.orm import Session

from mysite.db.models import Notifications


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
    for user_id in set(user_ids):
        if user_id is None:
            continue
        db.add(Notifications(user_id=user_id, title=title, body=body, link=link))

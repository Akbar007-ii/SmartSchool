"""Тесттер чыныгы PostgreSQL базасында, бирок бир транзакциянын ичинде иштейт
жана аягында толук ROLLBACK кылынат — базада эч кандай из калбайт."""
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["MEDIA_ROOT"] = tempfile.mkdtemp(prefix="smartschool_media_")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from main import app  # noqa: E402
from mysite.db.database import engine, get_db  # noqa: E402


@pytest.fixture(scope="module")
def db():
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture(scope="module")
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def freeze_time(monkeypatch):
    """Сервердик убакытты (Бишкек) токтотот: freeze_time(7, 30) же freeze_time(8, 0, days=1)."""
    from datetime import datetime, timedelta

    from mysite.services import timeutils

    real_today = datetime.now(timeutils.BISHKEK_TZ).date()

    def _freeze(hour, minute=0, second=0, days=0):
        frozen = datetime(
            real_today.year, real_today.month, real_today.day,
            hour, minute, second, tzinfo=timeutils.BISHKEK_TZ,
        ) + timedelta(days=days)

        class FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return frozen.astimezone(tz) if tz else frozen.replace(tzinfo=None)

        monkeypatch.setattr(timeutils, "datetime", FrozenDatetime)
        return frozen

    return _freeze

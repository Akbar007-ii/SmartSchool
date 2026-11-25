"""Сыр сөздү тандап табууга (brute force) каршы: ийгиликсиз аракеттерди чектөө.

Ар бир почта (логин) үчүн жана ар бир IP үчүн акыркы WINDOW_SECONDS ичиндеги
ийгиликсиз аракеттер саналат. Чек толсо, убакыт өткөнчө 429 кайтат.
Ийгиликтүү киргенде логиндин эсеби тазаланат.

Эсеп ар бир процесстин эс тутумунда сакталат: бир нече worker болсо,
ар бири өзүнчө эсептейт (чек ошончо эсе жумшак), бирок тандап табуу
баары бир иш жүзүндө мүмкүн эмес болуп калат.
"""
import hmac
import os
import threading
import time
from collections import deque

from fastapi import HTTPException, Request, status

MAX_FAILURES_PER_LOGIN = int(os.getenv("LOGIN_MAX_FAILURES", "10"))
MAX_FAILURES_PER_IP = int(os.getenv("LOGIN_MAX_FAILURES_PER_IP", "50"))
WINDOW_SECONDS = int(os.getenv("LOGIN_WINDOW_SECONDS", str(15 * 60)))

_failures: dict[str, deque] = {}
_lock = threading.Lock()


# Фронтенд (Vercel) менен сервердин ортосундагы жашыруун ачкыч. Коюлса, API'ге сайт аркылуу
# гана кирүүгө болот, ал эми кардардын IP дареги Vercel'ден келет (аны жасалмалоого болбойт).
PROXY_SECRET = os.getenv("PROXY_SECRET", "")


def is_trusted_proxy(request: Request) -> bool:
    return bool(PROXY_SECRET) and hmac.compare_digest(
        request.headers.get("x-proxy-secret", ""), PROXY_SECRET
    )


def client_ip(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    if is_trusted_proxy(request):
        return request.headers.get("x-client-ip", "").strip() or peer
    if PROXY_SECRET:
        return peer
    # Ачкыч коюлбаса (иштеп чыгуу, жергиликтүү демо) — мурдагыдай X-Forwarded-For'дон.
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    return forwarded or peer


def _recent(key: str, now: float) -> deque:
    attempts = _failures.setdefault(key, deque())
    while attempts and now - attempts[0] > WINDOW_SECONDS:
        attempts.popleft()
    return attempts


def ensure_not_blocked(login: str, ip: str) -> None:
    """Чек толгон болсо 429 кайтарат (сыр сөздү текшерүүдөн мурда чакырылат)."""
    now = time.monotonic()
    with _lock:
        for key, limit in ((f"login:{login}", MAX_FAILURES_PER_LOGIN), (f"ip:{ip}", MAX_FAILURES_PER_IP)):
            attempts = _recent(key, now)
            if len(attempts) >= limit:
                retry_after = int(WINDOW_SECONDS - (now - attempts[0])) + 1
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Өтө көп ийгиликсиз аракет. Бир аздан кийин кайра аракет кылыңыз",
                    headers={"Retry-After": str(retry_after)},
                )


def record_failure(login: str, ip: str) -> None:
    now = time.monotonic()
    with _lock:
        _recent(f"login:{login}", now).append(now)
        _recent(f"ip:{ip}", now).append(now)


def reset(login: str) -> None:
    with _lock:
        _failures.pop(f"login:{login}", None)

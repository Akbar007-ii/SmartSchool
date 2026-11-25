"""Файлдарды жүктөө (үй тапшырма сүрөттөрү, PDF, мектептин баннери, аватар)."""
import os
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT", Path(__file__).resolve().parents[2] / "media"))
MEDIA_URL = "/media"

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB (дизайн: «Макс. 10 MB»)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".txt"}

# Файлдын башындагы "сыйкырдуу" байттар — кеңейтүүсүн алмаштырып жүктөлгөн
# зыяндуу файлдардан коргоо үчүн.
_SIGNATURES = {
    ".jpg": [b"\xff\xd8\xff"],
    ".jpeg": [b"\xff\xd8\xff"],
    ".png": [b"\x89PNG\r\n\x1a\n"],
    ".webp": [b"RIFF"],
    ".pdf": [b"%PDF"],
    ".docx": [b"PK\x03\x04"],
    ".xlsx": [b"PK\x03\x04"],
    ".pptx": [b"PK\x03\x04"],
    ".doc": [b"\xd0\xcf\x11\xe0"],
    ".xls": [b"\xd0\xcf\x11\xe0"],
    ".ppt": [b"\xd0\xcf\x11\xe0"],
}


def is_image_url(url: str) -> bool:
    return Path(url).suffix.lower() in IMAGE_EXTENSIONS


def save_upload(
    upload: UploadFile,
    folder: str,
    allowed: set[str] | None = None,
) -> str:
    """Файлды сактап, анын URL дарегин кайтарат (мис: /media/homeworks/1/abc.jpg)."""
    allowed = allowed or (IMAGE_EXTENSIONS | DOCUMENT_EXTENSIONS)
    name = upload.filename or ""
    ext = Path(name).suffix.lower()

    if ext not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"«{name}» файлынын форматы колдоого алынбайт. "
                   f"Уруксат: {', '.join(sorted(allowed))}",
        )

    content = upload.file.read(MAX_FILE_SIZE + 1)
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail=f"«{name}» 10 MB ашпашы керек")
    if not content:
        raise HTTPException(status_code=400, detail=f"«{name}» бош файл")

    signatures = _SIGNATURES.get(ext)
    if signatures and not any(content.startswith(sig) for sig in signatures):
        raise HTTPException(
            status_code=400,
            detail=f"«{name}» файлынын мазмуну анын форматына дал келбейт",
        )

    target_dir = MEDIA_ROOT / folder
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{ext}"
    (target_dir / filename).write_bytes(content)

    return f"{MEDIA_URL}/{folder}/{filename}".replace("\\", "/")


def delete_media(url: str | None) -> None:
    if not url or not url.startswith(MEDIA_URL + "/"):
        return
    path = (MEDIA_ROOT / url[len(MEDIA_URL) + 1:]).resolve()
    if MEDIA_ROOT.resolve() in path.parents and path.is_file():
        path.unlink(missing_ok=True)


# =====================================================
# Үй тапшырмалардын файлдары — кол коюлган шилтемелер менен гана
# =====================================================
# Мугалимдин тапшырма файлдары жана окуучулардын жооптору жеке маалымат. Шилтемени API
# укугу бар колдонуучуга гана берет; ага мөөнөт жана кол (HMAC) кошулат. Мөөнөтү өткөн
# же колу жок шилтеме 404 кайтарат — шилтемени башка бирөөгө жөнөтсө, бир аздан кийин иштебейт.
import hashlib  # noqa: E402
import hmac  # noqa: E402
import time  # noqa: E402
from urllib.parse import parse_qs  # noqa: E402

from starlette.responses import PlainTextResponse  # noqa: E402
from starlette.staticfiles import StaticFiles  # noqa: E402

PROTECTED_FOLDERS = ("homeworks/", "submissions/")
SIGNED_URL_SECONDS = 6 * 60 * 60


def _signature(path: str, expires: int) -> str:
    key = (os.getenv("SECRET_KEY") or "").encode()
    return hmac.new(key, f"{path}|{expires}".encode(), hashlib.sha256).hexdigest()[:32]


def sign_media_url(url: str) -> str:
    """/media/homeworks/1/a.pdf → /media/homeworks/1/a.pdf?exp=...&sig=... (корголгон папкалар үчүн)."""
    path = url[len(MEDIA_URL) + 1:] if url.startswith(MEDIA_URL + "/") else ""
    if not path.startswith(PROTECTED_FOLDERS):
        return url
    # Шилтеме бир саатка тегеректелет: браузер файлды кэштен ала алат
    expires = (int(time.time()) // 3600 + 1) * 3600 + SIGNED_URL_SECONDS
    return f"{url}?exp={expires}&sig={_signature(path, expires)}"


def strip_signature(url: str) -> str:
    return url.split("?", 1)[0]


class ProtectedMediaFiles(StaticFiles):
    """Кадимки /media, бирок үй тапшырма папкалары туура кол коюлган шилтеме менен гана ачылат."""

    async def get_response(self, path: str, scope):
        normalized = path.replace("\\", "/").lstrip("/")
        if normalized.startswith(PROTECTED_FOLDERS):
            query = parse_qs(scope.get("query_string", b"").decode())
            try:
                expires = int(query.get("exp", ["0"])[0])
            except ValueError:
                expires = 0
            signature = query.get("sig", [""])[0]
            valid = expires > time.time() and hmac.compare_digest(signature, _signature(normalized, expires))
            if not valid:
                return PlainTextResponse("Not Found", status_code=404)
        return await super().get_response(path, scope)

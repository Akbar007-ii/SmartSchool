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

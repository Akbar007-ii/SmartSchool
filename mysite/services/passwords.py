"""Убактылуу сыр сөздөр.

Негизги сыр сөз ар дайым bcrypt менен хэштелет. Класс жетекчи жана завуч
убактылуу сыр сөздөрдү кийин тизме түрүндө алышы үчүн (ТЗ 6.1), убактылуу
сыр сөз SECRET_KEY'ден алынган ачкыч менен Fernet (AES) аркылуу шифрленип
сакталат жана колдонуучу биринчи киргенде сыр сөзүн алмаштырары менен өчүрүлөт.
"""
import base64
import hashlib
import secrets
import string
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from mysite.security.hashing import hash_password
from mysite.security.jwt import SECRET_KEY

_fernet = Fernet(
    base64.urlsafe_b64encode(
        hashlib.sha256(("temp-password:" + SECRET_KEY).encode("utf-8")).digest()
    )
)

# Окшош көрүнгөн белгилер (0/O, 1/l/I) алынып салынган — кагазга басып таратууга ыңгайлуу.
_ALPHABET = "".join(
    ch for ch in string.ascii_letters + string.digits if ch not in "0O1lI"
)


def generate_temp_password(length: int = 10) -> str:
    while True:
        password = "".join(secrets.choice(_ALPHABET) for _ in range(length))
        if (
            any(c.islower() for c in password)
            and any(c.isupper() for c in password)
            and any(c.isdigit() for c in password)
        ):
            return password


def encrypt_temp_password(password: str) -> str:
    return _fernet.encrypt(password.encode("utf-8")).decode("utf-8")


def decrypt_temp_password(token: Optional[str]) -> Optional[str]:
    if not token:
        return None
    try:
        return _fernet.decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return None


def set_temp_password(user, password: Optional[str] = None) -> str:
    """Колдонуучуга жаңы убактылуу сыр сөз коёт жана аны кайтарат."""
    password = password or generate_temp_password()
    user.hashed_password = hash_password(password)
    user.is_temp_password = True
    user.temp_password_encrypted = encrypt_temp_password(password)
    return password

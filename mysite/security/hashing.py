import bcrypt

# bcrypt сыр сөздүн биринчи 72 байтын гана колдонот, ал эми bcrypt 5 узунураагына ката чыгарат
# (кирүү барагы 500 катасы менен кулачу). Ошондуктан эки жакта тең 72 байтка чейин кесилет:
# мурунку хештерге таасири жок, алар баары 72 байттан кыска сыр сөздөрдөн түзүлгөн.
BCRYPT_MAX_BYTES = 72


def _password_bytes(password: str) -> bytes:
    return password.encode("utf-8")[:BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(_password_bytes(password), salt)
    return hashed.decode("utf-8")


def verify_password(
    plain_password: str,
    hashed_password: str
) -> bool:
    return bcrypt.checkpw(
        _password_bytes(plain_password),
        hashed_password.encode("utf-8")
    )

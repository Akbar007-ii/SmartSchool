
from mysite.security.hashing import (
    hash_password,
    verify_password
)

from mysite.security.jwt import (
    create_access_token,
    verify_access_token
)


# 1. Bcrypt тест
password = "Mektep#2026"

hashed = hash_password(password)

print("PASSWORD HASHED:", hashed[:20], "...")

print(
    "PASSWORD CHECK:",
    verify_password(password, hashed)
)


# 2. JWT тест
token = create_access_token({
    "sub": "1",
    "school_id": 1,
    "role": "STUDENT"
})

print("JWT CREATED:", bool(token))


# 3. JWT текшерүү
payload = verify_access_token(token)

print("JWT VERIFIED:", payload is not None)
print("USER ID:", payload["sub"] if payload else None)

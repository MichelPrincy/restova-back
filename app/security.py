import secrets
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.config import settings
from app.errors import unauthorized

_hasher = PasswordHasher()
# Hash factice : on vérifie quand même un mot de passe quand l'e-mail est inconnu,
# pour que le temps de réponse ne révèle pas quels comptes existent.
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def create_access_token(user_id: str) -> tuple[str, str, datetime]:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=settings.jwt_expire_minutes)
    jti = secrets.token_hex(16)
    token = jwt.encode(
        {"sub": user_id, "jti": jti, "typ": "access", "iat": now, "exp": exp},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    return token, jti, exp


def decode_access_token(token: str) -> dict:
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub", "jti"]},
        )
    except jwt.PyJWTError:
        raise unauthorized()
    if claims.get("typ") != "access":
        raise unauthorized()
    return claims

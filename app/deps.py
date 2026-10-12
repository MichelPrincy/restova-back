from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import AppError, unauthorized
from app.models import Restaurant, RevokedToken, User
from app.security import decode_access_token
from app.utils import ensure_utc

_bearer = HTTPBearer(auto_error=False)

DB = Annotated[Session, Depends(get_db)]


@dataclass
class AuthContext:
    user: User
    restaurant: Restaurant
    jti: str
    exp: datetime


def get_auth(
    db: DB,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AuthContext:
    if creds is None or creds.scheme.lower() != "bearer" or not creds.credentials:
        raise unauthorized()
    claims = decode_access_token(creds.credentials)

    if db.get(RevokedToken, claims["jti"]) is not None:
        raise unauthorized()
    user = db.get(User, claims["sub"])
    if user is None:
        raise unauthorized()
    restaurant = db.scalar(select(Restaurant).where(Restaurant.user_id == user.id))
    if restaurant is None:
        raise unauthorized()

    exp = ensure_utc(datetime.fromtimestamp(claims["exp"], tz=timezone.utc))
    return AuthContext(user=user, restaurant=restaurant, jti=claims["jti"], exp=exp)


def require_owner(auth: Annotated[AuthContext, Depends(get_auth)]) -> AuthContext:
    """Toutes les routes admin : jeton valide ET rôle propriétaire (sinon 403)."""
    if auth.user.role != "owner":
        raise AppError(403, "FORBIDDEN", "Accès refusé.")
    return auth


Auth = Annotated[AuthContext, Depends(get_auth)]
Owner = Annotated[AuthContext, Depends(require_owner)]

import logging

from fastapi import APIRouter, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.deps import DB, Auth
from app.errors import AppError, too_many_requests
from app.models import Restaurant, RevokedToken, User
from app.ratelimit import client_ip, enforce, limiter
from app.schemas import LoginIn, RegisterIn
from app.security import create_access_token, hash_password, verify_password
from app.serializers import restaurant_out, user_out
from app.utils import new_id, utcnow

router = APIRouter(prefix="/auth", tags=["auth"])
log = logging.getLogger("restova.auth")

LOGIN_WINDOW = 15 * 60
LOGIN_MAX_FAILURES = 8      # par (IP, e-mail)
LOGIN_MAX_PER_IP = 60       # tentatives totales par IP


def _session_payload(user: User, restaurant: Restaurant) -> dict:
    token, _, _ = create_access_token(user.id)
    return {"token": token, "user": user_out(user), "restaurant": restaurant_out(restaurant)}


@router.post("/register", status_code=201)
def register(payload: RegisterIn, request: Request, db: DB):
    enforce(f"register:{client_ip(request)}", limit=20, window=3600)

    if db.scalar(select(User.id).where(User.email == payload.email)) is not None:
        raise AppError(409, "EMAIL_ALREADY_IN_USE", "Un compte existe déjà avec cet e-mail.")

    user = User(id=new_id("usr"), email=payload.email, password_hash=hash_password(payload.password))
    try:
        db.add(user)
        db.flush()  # le user doit exister avant le restaurant (clé étrangère)
        restaurant = Restaurant(
            id=new_id("rst"), user_id=user.id, name=payload.restaurantName, address=payload.address,
            latitude=payload.latitude, longitude=payload.longitude, phone=payload.phone,
            logo_url=payload.logoUrl or "", email=payload.email,
        )
        db.add(restaurant)
        db.commit()
    except IntegrityError:  # course : même e-mail inscrit en parallèle
        db.rollback()
        raise AppError(409, "EMAIL_ALREADY_IN_USE", "Un compte existe déjà avec cet e-mail.")

    log.info("register user=%s restaurant=%s", user.id, restaurant.id)
    return _session_payload(user, restaurant)


@router.post("/login")
def login(payload: LoginIn, request: Request, db: DB):
    ip = client_ip(request)
    fail_key = f"login-fail:{ip}:{payload.email}"
    if limiter.count(fail_key, LOGIN_WINDOW) >= LOGIN_MAX_FAILURES:
        raise too_many_requests()
    enforce(f"login-ip:{ip}", limit=LOGIN_MAX_PER_IP, window=LOGIN_WINDOW)

    user = db.scalar(select(User).where(User.email == payload.email))
    # Même réponse (et même coût de calcul) que l'e-mail existe ou non.
    ok = verify_password(payload.password, user.password_hash if user else None)
    if not ok or user is None:
        limiter.hit(fail_key, LOGIN_WINDOW)
        raise AppError(401, "INVALID_CREDENTIALS", "Email ou mot de passe incorrect.")

    restaurant = db.scalar(select(Restaurant).where(Restaurant.user_id == user.id))
    if restaurant is None:
        raise AppError(401, "INVALID_CREDENTIALS", "Email ou mot de passe incorrect.")

    limiter.clear(fail_key)
    return _session_payload(user, restaurant)


@router.get("/me")
def me(auth: Auth):
    return {"user": user_out(auth.user), "restaurant": restaurant_out(auth.restaurant)}


@router.post("/logout", status_code=204)
def logout(auth: Auth, db: DB):
    if db.get(RevokedToken, auth.jti) is None:
        db.add(RevokedToken(jti=auth.jti, expires_at=auth.exp))
    db.execute(delete(RevokedToken).where(RevokedToken.expires_at < utcnow()))  # purge des expirés
    db.commit()
    return Response(status_code=204)

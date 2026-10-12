"""Routes publiques (sans compte) : carte client, commande, suivi."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from app.deps import DB
from app.errors import AppError, not_found, too_many_requests
from app.models import AccessLink, Category, MenuItem, Order, Restaurant
from app.ratelimit import client_ip, enforce, limiter
from app.schemas import PublicOrderIn
from app.serializers import category_out, menu_item_out, order_out, restaurant_out
from app.services.orders import place_order
from app.utils import ensure_utc, utcnow

FAIL_WINDOW = 10 * 60
FAIL_LIMIT = 30  # jetons invalides par IP et par fenêtre -> 429 (anti-énumération)


def _public_rate_limit(request: Request) -> None:
    enforce(f"public:{client_ip(request)}", limit=240, window=60)


router = APIRouter(prefix="/public", tags=["public"], dependencies=[Depends(_public_rate_limit)])


def _guard_enumeration(request: Request) -> str:
    ip = client_ip(request)
    if limiter.count(f"public-fail:{ip}", FAIL_WINDOW) >= FAIL_LIMIT:
        raise too_many_requests()
    return ip


def _resolve_link(db, token: str, request: Request) -> AccessLink:
    ip = _guard_enumeration(request)
    link = db.scalar(select(AccessLink).where(AccessLink.token == token))
    if link is None:
        limiter.hit(f"public-fail:{ip}", FAIL_WINDOW)
        raise AppError(404, "ACCESS_LINK_INVALID", "Ce lien n'est pas valide.")
    if link.revoked_at is not None:
        raise AppError(410, "ACCESS_LINK_REVOKED", "Ce lien a été désactivé par l'établissement.")
    expires = ensure_utc(link.expires_at)
    if expires is not None and expires <= utcnow():
        raise AppError(410, "ACCESS_LINK_EXPIRED", "Ce lien a expiré.")
    return link


@router.get("/access/{token}/menu")
def public_menu(token: str, request: Request, db: DB):
    link = _resolve_link(db, token, request)
    restaurant = db.get(Restaurant, link.restaurant_id)
    categories = db.scalars(
        select(Category).where(Category.restaurant_id == restaurant.id).order_by(Category.created_at, Category.id)
    ).all()
    # Plats « masqués » (isAvailable = false) : non exposés aux clients.
    items = db.scalars(
        select(MenuItem)
        .where(MenuItem.restaurant_id == restaurant.id, MenuItem.is_available.is_(True))
        .order_by(MenuItem.created_at, MenuItem.id)
    ).all()
    return {
        "restaurant": restaurant_out(restaurant, public=True),
        "categories": [category_out(c) for c in categories],
        "menuItems": [menu_item_out(m) for m in items],
        "tableNumber": link.table_number,
    }


@router.post("/access/{token}/orders", status_code=201)
def public_create_order(token: str, payload: PublicOrderIn, request: Request, db: DB):
    enforce(f"public-order:{client_ip(request)}", limit=10, window=60)
    link = _resolve_link(db, token, request)
    order = place_order(db, link, payload)
    return {"order": order_out(order)}


@router.get("/orders/{tracking_token}")
def public_track_order(tracking_token: str, request: Request, db: DB):
    ip = _guard_enumeration(request)
    order = db.scalar(select(Order).where(Order.tracking_token == tracking_token))
    if order is None:
        limiter.hit(f"public-fail:{ip}", FAIL_WINDOW)
        raise not_found("Commande introuvable.")
    # Fonctionne même si le lien d'accès a été révoqué depuis.
    return {"order": order_out(order)}

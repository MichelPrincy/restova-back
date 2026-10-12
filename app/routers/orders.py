from fastapi import APIRouter, Query
from sqlalchemy import select

from app.config import settings
from app.deps import DB, Owner
from app.errors import not_found
from app.models import Order
from app.schemas import OrderStatusIn
from app.serializers import order_out
from app.services.orders import change_status

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("")
def list_orders(
    auth: Owner,
    db: DB,
    limit: int | None = Query(default=None, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
):
    """Appelée toutes les 8 s par le front : une seule requête (+ selectin des lignes), plafonnée."""
    cap = min(limit or settings.orders_list_max, 5000)
    rows = db.scalars(
        select(Order).where(Order.restaurant_id == auth.restaurant.id)
        .order_by(Order.created_at.desc(), Order.id.desc())
        .limit(cap).offset(offset)
    ).all()
    return {"orders": [order_out(o) for o in rows]}


@router.patch("/{order_id}/status")
def update_status(order_id: str, payload: OrderStatusIn, auth: Owner, db: DB):
    order = db.scalar(
        select(Order).where(Order.id == order_id, Order.restaurant_id == auth.restaurant.id)
    )
    if order is None:
        raise not_found("Commande introuvable.")
    change_status(order, payload.status, payload.deliveryPersonName)
    db.commit()
    return {"order": order_out(order)}

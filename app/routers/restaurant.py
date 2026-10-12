from fastapi import APIRouter, Response
from sqlalchemy import delete, select

from app.deps import DB, Owner
from app.models import Category, MenuItem, Order, OrderItem, StockItem
from app.schemas import ProfileIn
from app.serializers import restaurant_out

router = APIRouter(prefix="/restaurant", tags=["restaurant"])


@router.put("/profile")
def update_profile(payload: ProfileIn, auth: Owner, db: DB):
    r = auth.restaurant  # toujours l'enseigne du jeton, jamais une autre
    r.name = payload.name
    r.address = payload.address
    r.latitude = payload.latitude
    r.longitude = payload.longitude
    r.phone = payload.phone
    r.logo_url = payload.logoUrl
    r.opening_hours = payload.openingHours
    r.currency = payload.currency
    r.email = payload.email or auth.user.email
    r.tagline = payload.tagline
    db.commit()
    return {"restaurant": restaurant_out(r)}


@router.delete("/data", status_code=204)
def purge_data(auth: Owner, db: DB):
    """Supprime catégories, plats, stock et commandes de l'enseigne (compte et profil conservés)."""
    rid = auth.restaurant.id
    order_ids = select(Order.id).where(Order.restaurant_id == rid)
    db.execute(delete(OrderItem).where(OrderItem.order_id.in_(order_ids)))
    db.execute(delete(Order).where(Order.restaurant_id == rid))
    db.execute(delete(MenuItem).where(MenuItem.restaurant_id == rid))
    db.execute(delete(Category).where(Category.restaurant_id == rid))
    db.execute(delete(StockItem).where(StockItem.restaurant_id == rid))
    db.commit()
    return Response(status_code=204)

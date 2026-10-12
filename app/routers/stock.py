from fastapi import APIRouter, Response
from sqlalchemy import case, select, update

from app.deps import DB, Owner
from app.errors import not_found, validation_error
from app.models import StockItem
from app.schemas import StockCreate, StockQuantityPatch
from app.serializers import stock_item_out
from app.utils import utcnow

router = APIRouter(prefix="/stock-items", tags=["stock"])


@router.get("")
def list_stock(auth: Owner, db: DB):
    rows = db.scalars(
        select(StockItem).where(StockItem.restaurant_id == auth.restaurant.id)
        .order_by(StockItem.name, StockItem.id)
    ).all()
    return {"stockItems": [stock_item_out(s) for s in rows]}


@router.post("", status_code=201)
def create_stock_item(payload: StockCreate, auth: Owner, db: DB):
    item = StockItem(
        restaurant_id=auth.restaurant.id, name=payload.name, category=payload.category,
        quantity=payload.quantity, unit=payload.unit, min_threshold=payload.minThreshold,
        cost_per_unit=payload.costPerUnit, supplier=(payload.supplier or "").strip() or None,
        last_updated=utcnow(),
    )
    db.add(item)
    db.commit()
    return {"stockItem": stock_item_out(item)}


@router.patch("/{item_id}/quantity")
def update_quantity(item_id: str, payload: StockQuantityPatch, auth: Owner, db: DB):
    has_delta = payload.delta is not None
    has_qty = payload.quantity is not None
    if has_delta == has_qty:
        raise validation_error(
            "Fournissez soit « delta », soit « quantity ».",
            {"quantity": "Exactement un champ parmi delta et quantity est attendu."},
        )

    if has_delta:
        # Atomique côté base : pas de lecture-modification-écriture, plancher à 0.
        new_qty = StockItem.quantity + payload.delta
        value = case((new_qty < 0, 0), else_=new_qty)
    else:
        value = payload.quantity

    res = db.execute(
        update(StockItem)
        .where(StockItem.id == item_id, StockItem.restaurant_id == auth.restaurant.id)
        .values(quantity=value, last_updated=utcnow())
        .execution_options(synchronize_session=False)
    )
    if res.rowcount == 0:
        db.rollback()
        raise not_found("Article de stock introuvable.")
    db.commit()

    item = db.execute(
        select(StockItem).where(StockItem.id == item_id).execution_options(populate_existing=True)
    ).scalar_one()
    return {"stockItem": stock_item_out(item)}


@router.delete("/{item_id}", status_code=204)
def delete_stock_item(item_id: str, auth: Owner, db: DB):
    item = db.scalar(
        select(StockItem).where(StockItem.id == item_id, StockItem.restaurant_id == auth.restaurant.id)
    )
    if item is None:
        raise not_found("Article de stock introuvable.")
    db.delete(item)
    db.commit()
    return Response(status_code=204)

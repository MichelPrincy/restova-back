from fastapi import APIRouter, Response
from sqlalchemy import func, select

from app.deps import DB, Owner
from app.errors import AppError, not_found
from app.models import Category, MenuItem
from app.schemas import CategoryCreate, CategoryPatch
from app.serializers import category_out

router = APIRouter(prefix="/categories", tags=["categories"])

DEFAULT_ICON = "🍽️"


def _get(db, auth, category_id: str) -> Category:
    cat = db.scalar(
        select(Category).where(Category.id == category_id, Category.restaurant_id == auth.restaurant.id)
    )
    if cat is None:
        raise not_found("Catégorie introuvable.")
    return cat


def _ensure_unique(db, auth, name: str, exclude_id: str | None = None) -> None:
    q = select(Category.id).where(
        Category.restaurant_id == auth.restaurant.id, func.lower(Category.name) == name.lower()
    )
    if exclude_id:
        q = q.where(Category.id != exclude_id)
    if db.scalar(q) is not None:
        raise AppError(409, "CATEGORY_ALREADY_EXISTS", "Une catégorie porte déjà ce nom.")


@router.get("")
def list_categories(auth: Owner, db: DB):
    rows = db.scalars(
        select(Category).where(Category.restaurant_id == auth.restaurant.id)
        .order_by(Category.created_at, Category.id)
    ).all()
    return {"categories": [category_out(c) for c in rows]}


@router.post("", status_code=201)
def create_category(payload: CategoryCreate, auth: Owner, db: DB):
    _ensure_unique(db, auth, payload.name)
    cat = Category(
        restaurant_id=auth.restaurant.id, name=payload.name,
        icon=payload.icon or DEFAULT_ICON, description=payload.description or None,
    )
    db.add(cat)
    db.commit()
    return {"category": category_out(cat)}


@router.patch("/{category_id}")
def update_category(category_id: str, payload: CategoryPatch, auth: Owner, db: DB):
    cat = _get(db, auth, category_id)
    sent = payload.model_fields_set
    if "name" in sent and payload.name is not None:
        _ensure_unique(db, auth, payload.name, exclude_id=cat.id)
        cat.name = payload.name
    if "icon" in sent and payload.icon is not None:
        cat.icon = payload.icon or DEFAULT_ICON
    if "description" in sent:
        cat.description = payload.description or None
    db.commit()
    return {"category": category_out(cat)}


@router.delete("/{category_id}", status_code=204)
def delete_category(category_id: str, auth: Owner, db: DB):
    cat = _get(db, auth, category_id)
    in_use = db.scalar(select(func.count()).select_from(MenuItem).where(MenuItem.category_id == cat.id))
    if in_use:
        raise AppError(409, "CATEGORY_NOT_EMPTY", "Cette catégorie contient encore des plats.")
    db.delete(cat)
    db.commit()
    return Response(status_code=204)

from fastapi import APIRouter, Response
from sqlalchemy import select

from app.deps import DB, Owner
from app.errors import not_found, validation_error
from app.models import Category, MenuItem
from app.schemas import MenuItemCreate, MenuItemPatch, OptionsIn
from app.serializers import menu_item_out
from app.utils import new_id, num

router = APIRouter(prefix="/menu-items", tags=["menu"])

SIMPLE_FIELDS = {
    "name": "name", "description": "description", "price": "price", "imageUrl": "image_url",
    "isAvailable": "is_available", "isPopular": "is_popular", "isSpicy": "is_spicy",
    "isVeggie": "is_veggie", "preparationTimeMinutes": "preparation_time_minutes",
}


def _options_to_dict(o: OptionsIn | None) -> dict:
    out: dict = {}
    if o is None:
        return out
    if o.sauces:
        out["sauces"] = list(dict.fromkeys(o.sauces))  # sans doublons, ordre conservé
    if o.extras:
        out["extras"] = [
            {"id": e.id or new_id("ext"), "name": e.name, "price": num(e.price)} for e in o.extras
        ]
    return out


def _check_category(db, auth, category_id: str) -> None:
    exists = db.scalar(
        select(Category.id).where(Category.id == category_id, Category.restaurant_id == auth.restaurant.id)
    )
    if exists is None:
        raise validation_error("Catégorie inconnue.", {"category": "Cette catégorie n'existe pas."})


def _get(db, auth, item_id: str) -> MenuItem:
    item = db.scalar(
        select(MenuItem).where(MenuItem.id == item_id, MenuItem.restaurant_id == auth.restaurant.id)
    )
    if item is None:
        raise not_found("Plat introuvable.")
    return item


@router.get("")
def list_menu_items(auth: Owner, db: DB):
    rows = db.scalars(
        select(MenuItem).where(MenuItem.restaurant_id == auth.restaurant.id)
        .order_by(MenuItem.created_at, MenuItem.id)
    ).all()
    return {"menuItems": [menu_item_out(m) for m in rows]}


@router.post("", status_code=201)
def create_menu_item(payload: MenuItemCreate, auth: Owner, db: DB):
    _check_category(db, auth, payload.category)
    item = MenuItem(
        restaurant_id=auth.restaurant.id, category_id=payload.category, name=payload.name,
        description=payload.description, price=payload.price, image_url=payload.imageUrl,
        is_available=payload.isAvailable, is_popular=payload.isPopular, is_spicy=payload.isSpicy,
        is_veggie=payload.isVeggie, preparation_time_minutes=payload.preparationTimeMinutes,
        ingredients=list(payload.ingredients), options=_options_to_dict(payload.options),
    )
    db.add(item)
    db.commit()
    return {"menuItem": menu_item_out(item)}


@router.patch("/{item_id}")
def update_menu_item(item_id: str, payload: MenuItemPatch, auth: Owner, db: DB):
    item = _get(db, auth, item_id)
    sent = payload.model_fields_set

    for api_name, column in SIMPLE_FIELDS.items():
        if api_name in sent and getattr(payload, api_name) is not None:
            setattr(item, column, getattr(payload, api_name))
    if "ingredients" in sent and payload.ingredients is not None:
        item.ingredients = list(payload.ingredients)
    if "options" in sent and payload.options is not None:
        item.options = _options_to_dict(payload.options)  # remplace l'objet options entier
    if "category" in sent and payload.category is not None:
        _check_category(db, auth, payload.category)
        item.category_id = payload.category
    db.commit()
    return {"menuItem": menu_item_out(item)}


@router.delete("/{item_id}", status_code=204)
def delete_menu_item(item_id: str, auth: Owner, db: DB):
    item = _get(db, auth, item_id)
    db.delete(item)  # les commandes passées gardent leur copie (nom, prix) ; menu_item_id -> NULL
    db.commit()
    return Response(status_code=204)

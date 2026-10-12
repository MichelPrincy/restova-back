"""Objets JSON du contrat (camelCase). Les champs « absents si vides » sont omis."""
from app.models import AccessLink, Category, MenuItem, Order, OrderItem, Restaurant, StockItem, User
from app.utils import ensure_utc, iso, num, utcnow


def user_out(u: User) -> dict:
    return {"id": u.id, "email": u.email}


def restaurant_out(r: Restaurant, public: bool = False) -> dict:
    out = {
        "id": r.id,
        "name": r.name,
        "address": r.address,
        "latitude": r.latitude,
        "longitude": r.longitude,
        "phone": r.phone,
        "logoUrl": r.logo_url or "",
        "openingHours": r.opening_hours or "",
        "currency": r.currency or "Ar",
        "tagline": r.tagline or "",
        "createdAt": iso(r.created_at),
    }
    if not public:  # l'e-mail du compte n'est jamais exposé sur les routes publiques
        out["email"] = r.email
    return out


def category_out(c: Category) -> dict:
    out = {"id": c.id, "name": c.name, "icon": c.icon}
    if c.description:  # « absente si vide »
        out["description"] = c.description
    return out


def menu_item_out(m: MenuItem) -> dict:
    options: dict = {}
    opts = m.options or {}
    if opts.get("sauces"):
        options["sauces"] = list(opts["sauces"])
    if opts.get("extras"):
        options["extras"] = [
            {"id": e["id"], "name": e["name"], "price": num(e["price"])} for e in opts["extras"]
        ]
    return {
        "id": m.id,
        "name": m.name,
        "description": m.description or "",
        "price": num(m.price),
        "category": m.category_id,
        "imageUrl": m.image_url or "",
        "isAvailable": m.is_available,
        "isPopular": m.is_popular,
        "isSpicy": m.is_spicy,
        "isVeggie": m.is_veggie,
        "preparationTimeMinutes": m.preparation_time_minutes,
        "ingredients": list(m.ingredients or []),
        "options": options,
    }


def stock_item_out(s: StockItem) -> dict:
    out = {
        "id": s.id,
        "name": s.name,
        "category": s.category,
        "quantity": num(s.quantity),
        "unit": s.unit,
        "minThreshold": num(s.min_threshold),
        "costPerUnit": num(s.cost_per_unit),
        "lastUpdated": iso(s.last_updated),
    }
    if s.supplier:
        out["supplier"] = s.supplier
    return out


def _order_item_out(i: OrderItem) -> dict:
    out = {
        "id": i.id,
        "menuItemId": i.menu_item_id,
        "name": i.name,
        "price": num(i.price),
        "imageUrl": i.image_url or "",
        "quantity": i.quantity,
        "selectedExtras": [
            {"id": e["id"], "name": e["name"], "price": num(e["price"])} for e in (i.selected_extras or [])
        ],
    }
    if i.selected_sauce:
        out["selectedSauce"] = i.selected_sauce
    if i.special_instructions:
        out["specialInstructions"] = i.special_instructions
    return out


def order_out(o: Order) -> dict:
    coords = None
    if o.delivery_lat is not None and o.delivery_lng is not None:
        coords = {"lat": o.delivery_lat, "lng": o.delivery_lng}
    out = {
        "id": o.id,
        "trackingToken": o.tracking_token,
        "orderNumber": o.order_number,
        "createdAt": iso(o.created_at),
        "customerName": o.customer_name,
        "customerPhone": o.customer_phone,
        "orderType": o.order_type,
        "tableNumber": o.table_number,
        "deliveryAddress": o.delivery_address,
        "deliveryCoordinates": coords,
        "deliveryDistanceKm": o.delivery_distance_km,
        "deliveryDurationMin": o.delivery_duration_min,
        "deliveryInstructions": o.delivery_instructions,
        "deliveryPersonName": o.delivery_person_name,
        "items": [_order_item_out(i) for i in o.items],
        "subtotal": num(o.subtotal),
        "tax": num(o.tax),
        "total": num(o.total),
        "status": o.status,
        "paymentMethod": o.payment_method,
        "isPaid": o.is_paid,
        "paymentStatus": o.payment_status,
        "paymentTransactionId": o.payment_transaction_id or "",
        "estimatedDeliveryMinutes": o.estimated_delivery_minutes,
        "note": o.note or "",
    }
    if o.payment_instructions:
        out["paymentInstructions"] = o.payment_instructions
    if o.payment_redirect_url and not o.is_paid and o.payment_status != "failed":
        out["paymentRedirectUrl"] = o.payment_redirect_url
    return out


def access_link_out(link: AccessLink, orders_count: int = 0) -> dict:
    return {
        "id": link.id,
        "token": link.token,
        "label": link.label,
        "tableNumber": link.table_number,
        "createdAt": iso(link.created_at),
        "expiresAt": iso(link.expires_at),
        "revokedAt": iso(link.revoked_at),
        "ordersCount": orders_count,
    }


def link_is_active(link: AccessLink) -> bool:
    if link.revoked_at is not None:
        return False
    exp = ensure_utc(link.expires_at)
    return exp is None or exp > utcnow()

"""Création de commande (prix recalculés côté serveur) et changements de statut."""
import logging
import secrets
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.errors import AppError, validation_error
from app.models import AccessLink, MenuItem, Order, OrderItem, Restaurant
from app.schemas import PublicOrderIn
from app.services.payments import PaymentInit, get_gateway
from app.utils import new_id

log = logging.getLogger("restova.orders")

MOBILE_MONEY = {"mvola", "orange_money", "airtel_money"}
TERMINAL_STATUSES = {"livree", "annulee"}
CENT = Decimal("0.01")


def _check_rules(data: PublicOrderIn) -> None:
    details: dict[str, str] = {}
    if data.orderType == "livraison":
        if not (data.deliveryAddress or "").strip():
            details["deliveryAddress"] = "L'adresse de livraison est obligatoire."
        if data.deliveryCoordinates is None:
            details["deliveryCoordinates"] = "La position de livraison est obligatoire."
    if data.paymentMethod in MOBILE_MONEY and not (data.payerPhone or "").strip():
        details["payerPhone"] = "Le numéro Mobile Money est obligatoire."
    if details:
        msg = next(iter(details.values())) if len(details) == 1 else "Certains champs sont invalides."
        raise validation_error(msg, details)


def place_order(db: Session, link: AccessLink, data: PublicOrderIn) -> Order:
    _check_rules(data)
    restaurant = db.get(Restaurant, link.restaurant_id)

    # --- plats : toujours relus en base (l'enseigne vient du lien, jamais du corps) ---
    wanted = {i.menuItemId for i in data.items}
    menu = {
        m.id: m
        for m in db.scalars(
            select(MenuItem).where(MenuItem.restaurant_id == restaurant.id, MenuItem.id.in_(wanted))
        )
    }
    missing = [i for i in data.items if i.menuItemId not in menu or not menu[i.menuItemId].is_available]
    if missing:
        names = ", ".join(f"« {i.name or i.menuItemId} »" for i in missing)
        raise AppError(
            422, "ITEM_UNAVAILABLE",
            f"Plat indisponible : {names}. Retirez-le de votre panier.",
            {"menuItemIds": [i.menuItemId for i in missing]},
        )

    lines: list[OrderItem] = []
    subtotal = Decimal("0")
    max_prep = 0
    for idx, it in enumerate(data.items):
        m = menu[it.menuItemId]
        opts = m.options or {}

        sauce = (it.selectedSauce or "").strip() or None
        if sauce and sauce not in (opts.get("sauces") or []):
            raise validation_error("Sauce inconnue pour ce plat.", {f"items.{idx}.selectedSauce": "Sauce inconnue."})

        extras_by_id = {e["id"]: e for e in (opts.get("extras") or [])}
        chosen: list[dict] = []
        for ref in it.selectedExtras:
            e = extras_by_id.get(ref.id)
            if e is None:
                raise validation_error("Supplément inconnu pour ce plat.",
                                       {f"items.{idx}.selectedExtras": "Supplément inconnu."})
            if all(c["id"] != e["id"] for c in chosen):  # doublons ignorés
                chosen.append({"id": e["id"], "name": e["name"], "price": e["price"]})

        unit = m.price + sum((Decimal(str(e["price"])) for e in chosen), Decimal("0"))
        subtotal += unit * it.quantity
        max_prep = max(max_prep, m.preparation_time_minutes or 0)
        lines.append(OrderItem(
            id=new_id("oit"), position=idx, menu_item_id=m.id, name=m.name, price=unit,
            image_url=m.image_url or "", quantity=it.quantity, selected_sauce=sauce,
            selected_extras=chosen, special_instructions=(it.specialInstructions or "").strip() or None,
        ))

    tax = (subtotal * Decimal(str(settings.tax_rate))).quantize(CENT, rounding=ROUND_HALF_UP)
    total = subtotal + tax

    # --- type de commande ---
    table = None
    address = lat = lng = None
    if data.orderType == "sur_place":
        table = link.table_number or (data.tableNumber or "").strip() or None  # la table du lien l'emporte
    elif data.orderType == "livraison":
        address = data.deliveryAddress.strip()
        lat, lng = data.deliveryCoordinates.lat, data.deliveryCoordinates.lng

    duration = round(data.deliveryDurationMin) if data.deliveryDurationMin is not None else None
    estimate = (max_prep or 10) + (duration or 0 if data.orderType == "livraison" else 0)

    # --- numéro séquentiel par enseigne (UPDATE atomique : le verrou de ligne sérialise) ---
    seq = db.execute(
        update(Restaurant)
        .where(Restaurant.id == restaurant.id)
        .values(order_seq=Restaurant.order_seq + 1)
        .returning(Restaurant.order_seq)
        .execution_options(synchronize_session=False)
    ).scalar_one()

    order = Order(
        id=new_id("ord"),
        restaurant_id=restaurant.id,
        access_link_id=link.id,
        tracking_token="tk_" + secrets.token_urlsafe(32),
        order_number=f"#R-{seq}",
        customer_name=data.customerName,
        customer_phone=data.customerPhone,
        order_type=data.orderType,
        table_number=table,
        delivery_address=address,
        delivery_lat=lat,
        delivery_lng=lng,
        delivery_distance_km=data.deliveryDistanceKm if data.orderType == "livraison" else None,
        delivery_duration_min=duration if data.orderType == "livraison" else None,
        delivery_instructions=(data.deliveryInstructions or "").strip() or None
        if data.orderType == "livraison" else None,
        subtotal=subtotal, tax=tax, total=total,
        status="recue",
        payment_method=data.paymentMethod,
        payer_phone=(data.payerPhone or "").strip() or None,
        is_paid=False,
        payment_status="cash" if data.paymentMethod == "especes" else "pending",
        estimated_delivery_minutes=estimate,
        note=(data.note or "").strip(),
        items=lines,
    )
    db.add(order)
    db.commit()  # la commande existe avant tout appel réseau vers le prestataire

    if data.paymentMethod != "especes":
        try:
            init = get_gateway().initiate(order, restaurant)
        except Exception:  # noqa: BLE001 - le prestataire ne doit pas faire perdre la commande
            log.exception("Échec d'initialisation du paiement pour %s", order.id)
            init = PaymentInit(
                transaction_id="", status="failed",
                instructions="Le service de paiement est indisponible. Contactez l'établissement.",
            )
        order.payment_transaction_id = init.transaction_id
        order.payment_instructions = init.instructions
        order.payment_redirect_url = init.redirect_url
        if init.status == "failed":
            order.payment_status = "failed"
        db.commit()

    log.info("order_created id=%s restaurant=%s link=%s", order.id, restaurant.id, link.id)
    return order


def change_status(order: Order, new_status: str, delivery_person: str | None) -> None:
    """Règles volontairement souples : seules les commandes terminées (livrée/annulée) sont figées."""
    if order.status != new_status and order.status in TERMINAL_STATUSES:
        raise AppError(
            409, "INVALID_STATUS_TRANSITION",
            "Cette commande est terminée : son statut ne peut plus être modifié.",
        )
    if (
        new_status == "en_preparation"
        and settings.require_payment_before_preparation
        and order.payment_status not in ("paid", "cash")
    ):
        raise AppError(409, "PAYMENT_REQUIRED", "Cette commande n'est pas encore payée.")
    order.status = new_status
    if delivery_person is not None:
        order.delivery_person_name = delivery_person.strip() or None

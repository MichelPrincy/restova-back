import logging
import secrets
from datetime import timedelta

from fastapi import APIRouter
from sqlalchemy import func, select

from app.deps import DB, Owner
from app.errors import not_found
from app.models import AccessLink, Order
from app.serializers import access_link_out
from app.schemas import AccessLinkCreate
from app.utils import new_id, utcnow

router = APIRouter(prefix="/access-links", tags=["access-links"])
audit = logging.getLogger("restova.audit")


def _get(db, auth, link_id: str) -> AccessLink:
    link = db.scalar(
        select(AccessLink).where(AccessLink.id == link_id, AccessLink.restaurant_id == auth.restaurant.id)
    )
    if link is None:
        raise not_found("Lien introuvable.")
    return link


@router.get("")
def list_links(auth: Owner, db: DB):
    links = db.scalars(
        select(AccessLink).where(AccessLink.restaurant_id == auth.restaurant.id)
        .order_by(AccessLink.created_at.desc(), AccessLink.id.desc())
    ).all()
    counts = dict(
        db.execute(
            select(Order.access_link_id, func.count())
            .where(Order.restaurant_id == auth.restaurant.id, Order.access_link_id.is_not(None))
            .group_by(Order.access_link_id)
        ).all()
    )
    return {"accessLinks": [access_link_out(l, counts.get(l.id, 0)) for l in links]}


@router.post("", status_code=201)
def create_link(payload: AccessLinkCreate, auth: Owner, db: DB):
    now = utcnow()
    link = AccessLink(
        id=new_id("lnk"),
        restaurant_id=auth.restaurant.id,
        token=secrets.token_urlsafe(32),  # 32 octets aléatoires, base64url
        label=(payload.label or "").strip() or None,
        table_number=(payload.tableNumber or "").strip() or None,
        created_at=now,
        expires_at=now + timedelta(hours=payload.expiresInHours) if payload.expiresInHours else None,
    )
    db.add(link)
    db.commit()
    audit.info("access_link_created id=%s restaurant=%s table=%s", link.id, auth.restaurant.id, link.table_number)
    return {"accessLink": access_link_out(link, 0)}


@router.post("/{link_id}/revoke")
def revoke_link(link_id: str, auth: Owner, db: DB):
    link = _get(db, auth, link_id)
    if link.revoked_at is None:
        link.revoked_at = utcnow()
        db.commit()
        audit.info("access_link_revoked id=%s restaurant=%s", link.id, auth.restaurant.id)
    count = db.scalar(select(func.count()).select_from(Order).where(Order.access_link_id == link.id)) or 0
    return {"accessLink": access_link_out(link, count)}

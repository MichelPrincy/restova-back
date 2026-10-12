"""Webhook de confirmation de paiement + simulateur de paiement (développement uniquement)."""
import hashlib
import hmac
import html
from typing import Literal

from fastapi import APIRouter, Header, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, ValidationError
from sqlalchemy import select

from app.config import settings
from app.deps import DB
from app.errors import AppError, not_found, validation_error
from app.models import AccessLink, Order
from app.services.payments import apply_payment_result

webhooks = APIRouter(tags=["payments"])
dev = APIRouter(prefix="/dev", tags=["dev-only"])


class WebhookIn(BaseModel):
    transactionId: str
    status: Literal["paid", "failed"]


@webhooks.post("/webhooks/payments")
async def payment_webhook(
    request: Request, db: DB, x_signature: str | None = Header(default=None)
):
    """Confirmation prestataire -> backend.

    Générique : corps JSON {"transactionId": "...", "status": "paid" | "failed"}, signé par
    HMAC-SHA256 (hex) du corps brut avec PAYMENT_WEBHOOK_SECRET, en-tête `X-Signature`.
    Chaque opérateur réel a son propre format/signature : adaptez cette route (ou ajoutez-en
    une par prestataire) en suivant leur documentation.
    """
    secret = settings.payment_webhook_secret
    if not secret:
        raise not_found()  # webhook désactivé tant qu'aucun secret n'est configuré
    raw = await request.body()
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    if not x_signature or not hmac.compare_digest(expected, x_signature.strip().lower()):
        raise AppError(401, "UNAUTHORIZED", "Signature invalide.")

    try:
        data = WebhookIn.model_validate_json(raw)
    except ValidationError:
        raise validation_error("Corps du webhook invalide.")
    order = db.scalar(select(Order).where(Order.payment_transaction_id == data.transactionId))
    if order is None:
        raise not_found("Transaction inconnue.")
    if apply_payment_result(order, data.status):
        db.commit()
    return {"ok": True}


# ---------------- simulateur (provider "mock", hors production) ----------------

@dev.get("/payments/{transaction_id}/checkout", response_class=HTMLResponse)
def mock_checkout(transaction_id: str, db: DB):
    order = db.scalar(select(Order).where(Order.payment_transaction_id == transaction_id))
    if order is None:
        raise not_found()
    txn = html.escape(order.payment_transaction_id)
    return HTMLResponse(
        f"<html><body style='font-family:sans-serif;max-width:420px;margin:40px auto'>"
        f"<h2>Paiement simulé</h2><p>Commande {html.escape(order.order_number)} — "
        f"transaction {txn}</p>"
        f"<p><a href='/dev/payments/{txn}/complete?result=paid'>✅ Simuler un paiement réussi</a></p>"
        f"<p><a href='/dev/payments/{txn}/complete?result=failed'>❌ Simuler un échec</a></p>"
        f"</body></html>"
    )


@dev.get("/payments/{transaction_id}/complete")
def mock_complete(transaction_id: str, db: DB, result: Literal["paid", "failed"] = "paid"):
    order = db.scalar(select(Order).where(Order.payment_transaction_id == transaction_id))
    if order is None:
        raise not_found()
    if apply_payment_result(order, result):
        db.commit()
    link = db.get(AccessLink, order.access_link_id) if order.access_link_id else None
    target = f"{settings.frontend_url}/?t={link.token}" if link else settings.frontend_url
    return RedirectResponse(target, status_code=303)

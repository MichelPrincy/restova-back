"""Paiement.

Le front ne décide jamais qu'une commande est payée : tout passe par `Order.payment_*`.

`PaymentGateway` est l'interface à implémenter pour chaque prestataire réel (MVola, Orange
Money, Airtel Money, carte). Les API de ces opérateurs demandent des comptes marchands et
des identifiants que je ne peux pas inventer : seul l'adaptateur `MockGateway` (développement)
est fourni. La confirmation réelle arrive par webhook -> `apply_payment_result`.
"""
import secrets
from dataclasses import dataclass
from typing import Protocol

from app.config import settings
from app.models import Order, Restaurant

OPERATOR_LABELS = {"mvola": "MVola", "orange_money": "Orange Money", "airtel_money": "Airtel Money"}


@dataclass
class PaymentInit:
    transaction_id: str
    status: str = "pending"  # pending | failed
    instructions: str | None = None
    redirect_url: str | None = None


class PaymentGateway(Protocol):
    def initiate(self, order: Order, restaurant: Restaurant) -> PaymentInit:
        """Lance la demande de paiement chez le prestataire (peut faire un appel réseau)."""
        ...


class MockGateway:
    """Développement uniquement : aucune somme n'est réellement débitée."""

    def initiate(self, order: Order, restaurant: Restaurant) -> PaymentInit:
        txn = "TXN-" + secrets.token_hex(6).upper()
        if order.payment_method == "carte_bancaire":
            return PaymentInit(
                transaction_id=txn,
                redirect_url=f"{settings.public_base_url}/dev/payments/{txn}/checkout",
            )
        label = OPERATOR_LABELS.get(order.payment_method, "Mobile Money")
        return PaymentInit(
            transaction_id=txn,
            instructions=f"Validez la demande de paiement {label} reçue sur le {order.payer_phone}.",
        )


def get_gateway() -> PaymentGateway:
    if settings.payment_provider == "mock":
        return MockGateway()
    raise RuntimeError(
        f"PAYMENT_PROVIDER={settings.payment_provider!r} : aucun adaptateur n'est implémenté. "
        "Ajoutez une classe respectant PaymentGateway dans app/services/payments.py."
    )


def apply_payment_result(order: Order, result: str) -> bool:
    """Applique la confirmation d'un prestataire. Idempotent. Renvoie True si l'état a changé.

    Seule une commande « pending » peut changer : un « paid » n'est jamais rétrogradé et
    une commande « cash » n'est pas concernée.
    """
    if order.payment_status != "pending":
        return False
    if result == "paid":
        order.is_paid = True
        order.payment_status = "paid"
        order.payment_instructions = None
        order.payment_redirect_url = None
    else:
        order.is_paid = False
        order.payment_status = "failed"
        order.payment_instructions = "Le paiement a été refusé."
        order.payment_redirect_url = None
    return True

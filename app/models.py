"""Modèles SQLAlchemy 2.0 — volontairement du PostgreSQL « standard » (aucune extension),
donc directement compatibles Supabase."""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, Numeric, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils import new_id, utcnow

JSONType = JSON().with_variant(JSONB(), "postgresql")


def _id(prefix: str):
    return mapped_column(String(32), primary_key=True, default=lambda: new_id(prefix))


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = _id("usr")
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="owner")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Restaurant(Base):
    __tablename__ = "restaurants"
    id: Mapped[str] = _id("rst")
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str] = mapped_column(String(500))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    phone: Mapped[str] = mapped_column(String(50))
    logo_url: Mapped[str] = mapped_column(String(2048), default="")
    opening_hours: Mapped[str] = mapped_column(String(500), default="")
    currency: Mapped[str] = mapped_column(String(10), default="Ar")
    email: Mapped[str] = mapped_column(String(320))
    tagline: Mapped[str] = mapped_column(String(500), default="")
    # compteur pour les numéros de commande séquentiels (#R-101, #R-102, ...)
    order_seq: Mapped[int] = mapped_column(Integer, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RevokedToken(Base):
    """Liste de révocation des JWT (POST /auth/logout)."""
    __tablename__ = "revoked_tokens"
    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Category(Base):
    __tablename__ = "categories"
    id: Mapped[str] = _id("cat")
    restaurant_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("restaurants.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    icon: Mapped[str] = mapped_column(String(16), default="🍽️")
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


Index("uq_categories_restaurant_lname", Category.restaurant_id, func.lower(Category.name), unique=True)


class MenuItem(Base):
    __tablename__ = "menu_items"
    id: Mapped[str] = _id("itm")
    restaurant_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("restaurants.id", ondelete="CASCADE"), index=True
    )
    category_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("categories.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    image_url: Mapped[str] = mapped_column(String(2048), default="")
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    is_popular: Mapped[bool] = mapped_column(Boolean, default=False)
    is_spicy: Mapped[bool] = mapped_column(Boolean, default=False)
    is_veggie: Mapped[bool] = mapped_column(Boolean, default=False)
    preparation_time_minutes: Mapped[int] = mapped_column(Integer, default=10)
    ingredients: Mapped[list] = mapped_column(JSONType, default=list)
    # {"sauces": ["Barbecue"], "extras": [{"id": "ext_1", "name": "Bacon", "price": 2000}]}
    options: Mapped[dict] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StockItem(Base):
    __tablename__ = "stock_items"
    id: Mapped[str] = _id("stk")
    restaurant_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("restaurants.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(120))
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    unit: Mapped[str] = mapped_column(String(30))
    min_threshold: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    cost_per_unit: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    supplier: Mapped[str | None] = mapped_column(String(200), nullable=True)
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AccessLink(Base):
    __tablename__ = "access_links"
    id: Mapped[str] = _id("lnk")
    restaurant_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("restaurants.id", ondelete="CASCADE"), index=True
    )
    # Le jeton est renvoyé à l'admin (GET /access-links) pour reconstruire l'URL / le QR :
    # il ne peut donc pas être seulement haché. Il est aléatoire (32 octets) et unique.
    token: Mapped[str] = mapped_column(String(64), unique=True)
    label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    table_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("restaurant_id", "order_number"),
        Index("ix_orders_restaurant_created", "restaurant_id", "created_at"),
    )
    id: Mapped[str] = _id("ord")
    restaurant_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("restaurants.id", ondelete="CASCADE")
    )
    access_link_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("access_links.id", ondelete="SET NULL"), nullable=True, index=True
    )
    tracking_token: Mapped[str] = mapped_column(String(64), unique=True)
    order_number: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    customer_name: Mapped[str] = mapped_column(String(200))
    customer_phone: Mapped[str] = mapped_column(String(50))
    order_type: Mapped[str] = mapped_column(String(20))  # sur_place | a_emporter | livraison
    table_number: Mapped[str | None] = mapped_column(String(30), nullable=True)

    delivery_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    delivery_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    delivery_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    delivery_distance_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    delivery_duration_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delivery_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivery_person_name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    tax: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    status: Mapped[str] = mapped_column(String(20), default="recue")

    payment_method: Mapped[str] = mapped_column(String(20))
    payer_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_paid: Mapped[bool] = mapped_column(Boolean, default=False)
    payment_status: Mapped[str] = mapped_column(String(20), default="pending")
    payment_transaction_id: Mapped[str] = mapped_column(String(100), default="", index=True)
    payment_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_redirect_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    estimated_delivery_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")

    items: Mapped[list["OrderItem"]] = relationship(
        order_by="OrderItem.position", cascade="all, delete-orphan", lazy="selectin"
    )


class OrderItem(Base):
    """Copie figée (nom, prix) au moment de la commande."""
    __tablename__ = "order_items"
    id: Mapped[str] = _id("oit")
    order_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("orders.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    menu_item_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("menu_items.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(200))
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))  # prix unitaire extras inclus
    image_url: Mapped[str] = mapped_column(String(2048), default="")
    quantity: Mapped[int] = mapped_column(Integer)
    selected_sauce: Mapped[str | None] = mapped_column(String(120), nullable=True)
    selected_extras: Mapped[list] = mapped_column(JSONType, default=list)
    special_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)

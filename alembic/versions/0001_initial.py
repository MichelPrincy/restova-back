"""Schéma initial Restova

Revision ID: 0001
Revises:
Create Date: 2026-10-12
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

JSONType = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")
TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_table(
        "restaurants",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("address", sa.String(500), nullable=False),
        sa.Column("latitude", sa.Float, nullable=False),
        sa.Column("longitude", sa.Float, nullable=False),
        sa.Column("phone", sa.String(50), nullable=False),
        sa.Column("logo_url", sa.String(2048), nullable=False),
        sa.Column("opening_hours", sa.String(500), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("tagline", sa.String(500), nullable=False),
        sa.Column("order_seq", sa.Integer, nullable=False),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_table(
        "revoked_tokens",
        sa.Column("jti", sa.String(64), primary_key=True),
        sa.Column("expires_at", TS, nullable=False),
    )
    op.create_index("ix_revoked_tokens_expires_at", "revoked_tokens", ["expires_at"])

    op.create_table(
        "categories",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("restaurant_id", sa.String(32), sa.ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("icon", sa.String(16), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_index("ix_categories_restaurant_id", "categories", ["restaurant_id"])
    op.create_index(
        "uq_categories_restaurant_lname", "categories", ["restaurant_id", sa.text("lower(name)")], unique=True
    )

    op.create_table(
        "menu_items",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("restaurant_id", sa.String(32), sa.ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category_id", sa.String(32), sa.ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("image_url", sa.String(2048), nullable=False),
        sa.Column("is_available", sa.Boolean, nullable=False),
        sa.Column("is_popular", sa.Boolean, nullable=False),
        sa.Column("is_spicy", sa.Boolean, nullable=False),
        sa.Column("is_veggie", sa.Boolean, nullable=False),
        sa.Column("preparation_time_minutes", sa.Integer, nullable=False),
        sa.Column("ingredients", JSONType, nullable=False),
        sa.Column("options", JSONType, nullable=False),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_index("ix_menu_items_restaurant_id", "menu_items", ["restaurant_id"])
    op.create_index("ix_menu_items_category_id", "menu_items", ["category_id"])

    op.create_table(
        "stock_items",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("restaurant_id", sa.String(32), sa.ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(120), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("unit", sa.String(30), nullable=False),
        sa.Column("min_threshold", sa.Numeric(14, 3), nullable=False),
        sa.Column("cost_per_unit", sa.Numeric(14, 2), nullable=False),
        sa.Column("supplier", sa.String(200), nullable=True),
        sa.Column("last_updated", TS, nullable=False),
    )
    op.create_index("ix_stock_items_restaurant_id", "stock_items", ["restaurant_id"])

    op.create_table(
        "access_links",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("restaurant_id", sa.String(32), sa.ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token", sa.String(64), nullable=False, unique=True),
        sa.Column("label", sa.String(120), nullable=True),
        sa.Column("table_number", sa.String(30), nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("expires_at", TS, nullable=True),
        sa.Column("revoked_at", TS, nullable=True),
    )
    op.create_index("ix_access_links_restaurant_id", "access_links", ["restaurant_id"])

    op.create_table(
        "orders",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("restaurant_id", sa.String(32), sa.ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("access_link_id", sa.String(32), sa.ForeignKey("access_links.id", ondelete="SET NULL"), nullable=True),
        sa.Column("tracking_token", sa.String(64), nullable=False, unique=True),
        sa.Column("order_number", sa.String(20), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("customer_name", sa.String(200), nullable=False),
        sa.Column("customer_phone", sa.String(50), nullable=False),
        sa.Column("order_type", sa.String(20), nullable=False),
        sa.Column("table_number", sa.String(30), nullable=True),
        sa.Column("delivery_address", sa.String(500), nullable=True),
        sa.Column("delivery_lat", sa.Float, nullable=True),
        sa.Column("delivery_lng", sa.Float, nullable=True),
        sa.Column("delivery_distance_km", sa.Float, nullable=True),
        sa.Column("delivery_duration_min", sa.Integer, nullable=True),
        sa.Column("delivery_instructions", sa.Text, nullable=True),
        sa.Column("delivery_person_name", sa.String(200), nullable=True),
        sa.Column("subtotal", sa.Numeric(14, 2), nullable=False),
        sa.Column("tax", sa.Numeric(14, 2), nullable=False),
        sa.Column("total", sa.Numeric(14, 2), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("payment_method", sa.String(20), nullable=False),
        sa.Column("payer_phone", sa.String(50), nullable=True),
        sa.Column("is_paid", sa.Boolean, nullable=False),
        sa.Column("payment_status", sa.String(20), nullable=False),
        sa.Column("payment_transaction_id", sa.String(100), nullable=False),
        sa.Column("payment_instructions", sa.Text, nullable=True),
        sa.Column("payment_redirect_url", sa.String(2048), nullable=True),
        sa.Column("estimated_delivery_minutes", sa.Integer, nullable=True),
        sa.Column("note", sa.Text, nullable=False),
        sa.UniqueConstraint("restaurant_id", "order_number"),
    )
    op.create_index("ix_orders_restaurant_created", "orders", ["restaurant_id", "created_at"])
    op.create_index("ix_orders_access_link_id", "orders", ["access_link_id"])
    op.create_index("ix_orders_payment_transaction_id", "orders", ["payment_transaction_id"])

    op.create_table(
        "order_items",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("order_id", sa.String(32), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("menu_item_id", sa.String(32), sa.ForeignKey("menu_items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("image_url", sa.String(2048), nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("selected_sauce", sa.String(120), nullable=True),
        sa.Column("selected_extras", JSONType, nullable=False),
        sa.Column("special_instructions", sa.Text, nullable=True),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])


def downgrade() -> None:
    for table in (
        "order_items", "orders", "access_links", "stock_items", "menu_items",
        "categories", "revoked_tokens", "restaurants", "users",
    ):
        op.drop_table(table)

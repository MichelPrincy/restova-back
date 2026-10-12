import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import DEFAULT_JWT_SECRET, settings
from app.database import Base, engine
from app.deps import DB
from app.errors import register_error_handlers
from app.routers import (
    access_links, auth, categories, menu_items, orders, payments, public, restaurant, stock,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("restova")


def _check_startup_config() -> None:
    if settings.is_production:
        if settings.jwt_secret == DEFAULT_JWT_SECRET or len(settings.jwt_secret) < 32:
            raise RuntimeError("JWT_SECRET doit être défini (32 caractères minimum) en production.")
        if settings.payment_provider == "mock":
            log.warning(
                "PAYMENT_PROVIDER=mock en production : les paiements mobiles/cartes resteront « pending »."
            )
    elif settings.jwt_secret == DEFAULT_JWT_SECRET:
        log.warning("JWT_SECRET par défaut : acceptable en développement seulement.")


@asynccontextmanager
async def lifespan(_: FastAPI):
    _check_startup_config()
    if settings.auto_create_tables:
        import app.models  # noqa: F401  (enregistre les tables)
        Base.metadata.create_all(engine)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Restova API",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,  # jeton Bearer dans l'en-tête, pas de cookies
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
        max_age=600,
    )
    register_error_handlers(app)

    for r in (auth, restaurant, categories, menu_items, stock, orders, access_links, public):
        app.include_router(r.router)
    app.include_router(payments.webhooks)
    if settings.payment_provider == "mock" and not settings.is_production:
        app.include_router(payments.dev)

    @app.get("/health", tags=["health"])
    def health(db: DB):
        db.execute(text("SELECT 1"))
        return {"status": "ok"}

    return app


app = create_app()

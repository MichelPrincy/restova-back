"""Configuration (variables d'environnement / fichier .env)."""
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_JWT_SECRET = "change-me-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "development"  # development | production

    # PostgreSQL local, Supabase plus tard : seule cette URL change.
    database_url: str = "postgresql://postgres.ldccbaapwmsdswobsexa:XnyMichelPrincy.2709@aws-0-eu-west-1.pooler.supabase.com:5432/postgres"
    db_echo: bool = False
    auto_create_tables: bool = False  # pratique en dev ; en prod : Alembic

    jwt_secret: str = DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7

    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://192.168.1.67:3000"
    frontend_url: str = "http://localhost:5173"
    public_base_url: str = "http://localhost:8000"

    tax_rate: float = 0.0  # ex. 0.20 pour 20 %
    orders_list_max: int = 500  # plafond de GET /orders (polling toutes les 8 s)
    require_payment_before_preparation: bool = False

    payment_provider: str = "mock"  # "mock" tant qu'aucun adaptateur réel n'est branché
    payment_webhook_secret: str = ""  # vide = webhook désactivé

    @field_validator("database_url")
    @classmethod
    def _normalize_db_url(cls, v: str) -> str:
        # Supabase / Heroku fournissent "postgresql://" ou "postgres://"
        if v.startswith("postgres://"):
            v = "postgresql://" + v[len("postgres://"):]
        if v.startswith("postgresql://"):
            v = "postgresql+psycopg://" + v[len("postgresql://"):]
        return v

    @property
    def is_production(self) -> bool:
        return self.env.lower() == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()

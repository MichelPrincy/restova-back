from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

from app.config import settings


class Base(DeclarativeBase):
    pass


def build_engine(url: str, echo: bool = False) -> Engine:
    kwargs: dict = {"echo": echo}
    connect_args: dict = {}

    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        if ":memory:" in url or url.rstrip("/").endswith("sqlite:"):
            kwargs["poolclass"] = StaticPool
    elif "pooler.supabase.com" in url or ":6543/" in url:
        # Supabase « transaction pooler » (pgbouncer) : le pooling est fait côté Supabase,
        # et les requêtes préparées de psycopg3 ne sont pas supportées dans ce mode.
        kwargs["poolclass"] = NullPool
        connect_args["prepare_threshold"] = None
    else:
        kwargs.update(pool_size=10, max_overflow=10, pool_pre_ping=True, pool_recycle=1800)

    engine = create_engine(url, connect_args=connect_args, **kwargs)

    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _enable_fk(dbapi_conn, _):  # noqa: ANN001
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return engine


engine = build_engine(settings.database_url, settings.db_echo)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

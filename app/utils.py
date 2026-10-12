import secrets
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(dt: datetime | None) -> datetime | None:
    """SQLite renvoie des datetimes naïfs ; PostgreSQL des datetimes avec fuseau."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso(dt: datetime | None) -> str | None:
    """ISO 8601 UTC avec millisecondes : 2026-10-12T09:20:00.000Z"""
    dt = ensure_utc(dt)
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def num(v: Any) -> int | float | None:
    """Decimal -> int si entier (18000), sinon float (12.5)."""
    if v is None:
        return None
    d = v if isinstance(v, Decimal) else Decimal(str(v))
    return int(d) if d == d.to_integral_value() else float(d)

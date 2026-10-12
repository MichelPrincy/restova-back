"""Rate limiting en mémoire (fenêtre glissante).

Suffisant pour une seule instance. Avec plusieurs workers/instances, chaque processus
a son propre compteur : remplacer par Redis (ex. slowapi + redis) le moment venu.
"""
import threading
import time
from collections import defaultdict, deque

from fastapi import Request

from app.errors import too_many_requests


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, window: float, now: float) -> deque[float]:
        q = self._hits[key]
        while q and q[0] <= now - window:
            q.popleft()
        return q

    def count(self, key: str, window: float) -> int:
        with self._lock:
            return len(self._prune(key, window, time.monotonic()))

    def hit(self, key: str, window: float) -> int:
        """Enregistre un événement et renvoie le nombre d'événements dans la fenêtre."""
        now = time.monotonic()
        with self._lock:
            q = self._prune(key, window, now)
            q.append(now)
            if len(self._hits) > 20000:  # évite une croissance sans limite
                for k in [k for k, v in self._hits.items() if not v or v[-1] <= now - 3600]:
                    del self._hits[k]
            return len(q)

    def clear(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def reset_all(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def client_ip(request: Request) -> str:
    # Derrière un proxy, lancer uvicorn avec --proxy-headers (X-Forwarded-For).
    return request.client.host if request.client else "unknown"


def enforce(key: str, limit: int, window: float) -> None:
    """Compte l'appel et lève 429 au-delà de `limit` appels dans `window` secondes."""
    if limiter.hit(key, window) > limit:
        raise too_many_requests()

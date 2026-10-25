"""API-key auth, cron secret and a small in-memory rate limiter."""
import hmac
import logging
import time
from collections import defaultdict, deque
from typing import Deque, Dict

from fastapi import Depends, Header, HTTPException, Request

from app.config import settings

logger = logging.getLogger(__name__)


def _same(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


async def require_api_key(x_api_key: str = Header(default="")) -> None:
    """Require `X-API-Key` when API_KEY is configured.

    With API_KEY unset the API is open (local development only);
    REQUIRE_AUTH=true makes startup fail instead (see main.py).
    """
    expected = settings.API_KEY
    if not expected:
        return
    if not x_api_key or not _same(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


async def require_cron_secret(authorization: str = Header(default=""),
                              x_api_key: str = Header(default="")) -> None:
    """Cron trigger auth: `Authorization: Bearer <CRON_SECRET>` (Vercel style)
    or the regular API key. Open only when neither secret is configured (dev)."""
    secret, key = settings.CRON_SECRET, settings.API_KEY
    if not secret and not key:
        return
    if secret and authorization.startswith("Bearer ") and _same(authorization[7:], secret):
        return
    if key and x_api_key and _same(x_api_key, key):
        return
    raise HTTPException(status_code=401, detail="Invalid or missing credentials")


class RateLimiter:
    """Sliding-window per-client limiter (single process)."""

    def __init__(self, limit: int, window: float = 60.0, name: str = "rl"):
        self.limit = limit
        self.window = window
        self.hits: Dict[str, Deque[float]] = defaultdict(deque)

    async def __call__(self, request: Request) -> None:
        client = request.client.host if request.client else "unknown"
        now = time.monotonic()
        q = self.hits[client]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            raise HTTPException(status_code=429, detail="Too many requests")
        q.append(now)


expensive_limit = RateLimiter(limit=6, window=60.0)
general_limit = RateLimiter(limit=240, window=60.0)

auth_dependencies = [Depends(require_api_key), Depends(general_limit)]

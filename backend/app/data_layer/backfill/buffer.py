"""
Buffer for WebSocket candles received while the backfill manager is still
catching up, so the backfill -> live transition doesn't drop data
(___DataLayer.md section 7, step 7).
"""
import asyncio
from typing import List, Tuple

from app.data_layer.core.models import Candle


class WsBuffer:
    """Collects (candle, is_closed) tuples while `enabled`, for later flush."""

    def __init__(self):
        self._items: List[Tuple[Candle, bool]] = []
        self._lock = asyncio.Lock()
        self.enabled = True

    async def add(self, candle: Candle, is_closed: bool) -> bool:
        """Add an item if buffering is enabled. Returns True if buffered."""
        if not self.enabled:
            return False
        async with self._lock:
            self._items.append((candle, is_closed))
        return True

    async def flush(self) -> List[Tuple[Candle, bool]]:
        """Disable buffering and return everything collected so far."""
        async with self._lock:
            self.enabled = False
            items, self._items = self._items, []
        return items

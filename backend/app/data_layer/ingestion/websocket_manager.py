"""
Generic WebSocket connection manager.

Implements the reconnect/heartbeat requirements from ___DataLayer.md section 6:
- Exponential backoff on reconnect: 1s -> 2s -> 4s -> ... -> max (default 60s)
- Periodic ping heartbeat
- Logs the exact disconnect/reconnect timestamps so callers can run gap-fill
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

import websockets

logger = logging.getLogger(__name__)

OnMessage = Callable[[str], Awaitable[None]]
OnReconnect = Callable[[Optional[datetime], datetime], Awaitable[None]]


class WebSocketManager:
    """Maintains a single resilient WebSocket connection."""

    def __init__(
        self,
        url: str,
        on_message: OnMessage,
        on_reconnect: Optional[OnReconnect] = None,
        backoff_min: float = 1.0,
        backoff_max: float = 60.0,
        heartbeat_interval: float = 20.0,
        name: str = "ws",
    ):
        self.url = url
        self.on_message = on_message
        self.on_reconnect = on_reconnect
        self.backoff_min = backoff_min
        self.backoff_max = backoff_max
        self.heartbeat_interval = heartbeat_interval
        self.name = name

        self._stop = False
        self._disconnected_at: Optional[datetime] = None

    async def run(self):
        """Connect and process messages until stop() is called.

        Reconnects with exponential backoff on any error, and notifies
        `on_reconnect(disconnected_at, reconnected_at)` so callers can fetch
        any data missed during the gap.
        """
        backoff = self.backoff_min
        while not self._stop:
            try:
                async with websockets.connect(self.url, ping_interval=self.heartbeat_interval) as ws:
                    logger.info(f"[{self.name}] connected to {self.url}")

                    if self._disconnected_at is not None:
                        reconnected_at = datetime.now(timezone.utc)
                        if self.on_reconnect:
                            await self.on_reconnect(self._disconnected_at, reconnected_at)
                        self._disconnected_at = None

                    backoff = self.backoff_min

                    while not self._stop:
                        message = await ws.recv()
                        await self.on_message(message)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self._disconnected_at = datetime.now(timezone.utc)
                logger.warning(
                    f"[{self.name}] disconnected ({e}); reconnecting in {backoff:.1f}s"
                )
                if self._stop:
                    break
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self.backoff_max)

    def stop(self):
        self._stop = True

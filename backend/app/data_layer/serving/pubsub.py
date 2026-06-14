"""
Redis pub/sub publishing for live updates (___DataLayer.md section 10).

Channels (v1 subset):
  ticker:{symbol}                    -> ticker update
  candle:closed:{symbol}:{timeframe} -> a candle just closed
  indicators:{symbol}:{timeframe}    -> indicators recomputed
"""
import json

import redis.asyncio as aioredis

from app.data_layer.core.config import settings
from app.data_layer.core.models import Candle, Ticker


class PubSub:
    def __init__(self, redis_url: str | None = None):
        self._redis = aioredis.from_url(redis_url or settings.REDIS_URL, decode_responses=True)

    async def close(self):
        await self._redis.aclose()

    async def publish_ticker(self, ticker: Ticker):
        await self._redis.publish(f"ticker:{ticker.symbol}", json.dumps(ticker.to_dict()))

    async def publish_candle_closed(self, candle: Candle):
        channel = f"candle:closed:{candle.symbol}:{candle.timeframe}"
        await self._redis.publish(channel, json.dumps(candle.to_dict()))

    async def publish_indicators(self, symbol: str, timeframe: str, values: dict):
        channel = f"indicators:{symbol}:{timeframe}"
        await self._redis.publish(channel, json.dumps(values))

    def subscribe(self):
        """Return a new redis pubsub object for consumers to `.subscribe(...)` on."""
        return self._redis.pubsub()

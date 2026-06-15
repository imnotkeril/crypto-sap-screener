"""
Redis real-time state store.

Key schema (___DataLayer.md section 8):
  ticker:{exchange}:{symbol}              -> Hash, last Ticker, TTL 10s
  candles:{exchange}:{symbol}:{timeframe} -> Sorted Set, last N candles (score=timestamp)
  indicators:{symbol}:{timeframe}         -> Hash, latest indicator values, no TTL
"""
import json
import logging
from typing import List, Optional

import redis.asyncio as aioredis

from app.data_layer.core.config import settings
from app.data_layer.core.models import Candle, Ticker

logger = logging.getLogger(__name__)


def _ticker_key(exchange: str, symbol: str) -> str:
    return f"ticker:{exchange}:{symbol}"


def _candles_key(exchange: str, symbol: str, timeframe: str) -> str:
    return f"candles:{exchange}:{symbol}:{timeframe}"


def _indicators_key(symbol: str, timeframe: str) -> str:
    return f"indicators:{symbol}:{timeframe}"


class RedisStore:
    def __init__(self, redis_url: Optional[str] = None):
        self._redis = aioredis.from_url(redis_url or settings.REDIS_URL, decode_responses=True)

    async def ping(self):
        await self._redis.ping()

    async def close(self):
        await self._redis.aclose()

    # -- Ticker -----------------------------------------------------------

    async def set_ticker(self, ticker: Ticker):
        key = _ticker_key(ticker.exchange, ticker.symbol)
        await self._redis.set(key, json.dumps(ticker.to_dict()), ex=settings.DATALAYER_TICKER_TTL)

    async def get_ticker(self, exchange: str, symbol: str) -> Optional[dict]:
        raw = await self._redis.get(_ticker_key(exchange, symbol))
        return json.loads(raw) if raw else None

    # -- Candles ------------------------------------------------------------

    async def add_candle(self, candle: Candle):
        key = _candles_key(candle.exchange, candle.symbol, candle.timeframe)
        score = candle.timestamp.timestamp()
        await self._redis.zadd(key, {json.dumps(candle.to_dict()): score})

        # Trim to keep only the most recent N candles
        count = await self._redis.zcard(key)
        limit = settings.DATALAYER_REDIS_CANDLE_LIMIT
        if count > limit:
            await self._redis.zremrangebyrank(key, 0, count - limit - 1)

    async def get_latest_candles(self, exchange: str, symbol: str, timeframe: str, limit: int = 100) -> List[dict]:
        key = _candles_key(exchange, symbol, timeframe)
        raw_items = await self._redis.zrange(key, -limit, -1)
        return [json.loads(item) for item in raw_items]

    # -- Indicators ---------------------------------------------------------

    async def set_indicators(self, symbol: str, timeframe: str, values: dict):
        key = _indicators_key(symbol, timeframe)
        # Redis hashes require flat str -> str mappings
        flat = {k: json.dumps(v) for k, v in values.items()}
        await self._redis.hset(key, mapping=flat)

    async def get_indicators(self, symbol: str, timeframe: str) -> dict:
        key = _indicators_key(symbol, timeframe)
        raw = await self._redis.hgetall(key)
        return {k: json.loads(v) for k, v in raw.items()}

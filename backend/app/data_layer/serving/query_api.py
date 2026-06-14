"""
Query API (___DataLayer.md section 10) - historical queries against
Postgres and current-state lookups against Redis.
"""
from datetime import datetime, timezone
from typing import List, Optional

from app.data_layer.storage.postgres_store import PostgresStore
from app.data_layer.storage.redis_store import RedisStore


class QueryAPI:
    def __init__(self, pg: PostgresStore, redis: RedisStore, default_exchange: str = "binance"):
        self._pg = pg
        self._redis = redis
        self._default_exchange = default_exchange

    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: Optional[datetime] = None,
        exchange: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[dict]:
        return await self._pg.get_candles(symbol, timeframe, start, end, exchange, limit)

    async def get_latest_candles(self, symbol: str, timeframe: str, limit: int = 100, exchange: Optional[str] = None) -> List[dict]:
        return await self._redis.get_latest_candles(exchange or self._default_exchange, symbol, timeframe, limit)

    async def get_ticker(self, symbol: str, exchange: Optional[str] = None) -> Optional[dict]:
        return await self._redis.get_ticker(exchange or self._default_exchange, symbol)

    async def get_indicators(self, symbol: str, timeframe: str) -> dict:
        return await self._redis.get_indicators(symbol, timeframe)

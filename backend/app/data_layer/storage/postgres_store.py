"""
Postgres historical store for candles.

Schema follows ___DataLayer.md section 8, adapted to plain Postgres (the
existing Supabase database). If the `timescaledb` extension is available the
table is converted to a hypertable for better performance; otherwise it
falls back to a regular table with an index, which is functionally fine at
this data volume (a handful of symbols/timeframes).
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional

import asyncpg

from app.data_layer.core.config import settings
from app.data_layer.core.models import Candle

logger = logging.getLogger(__name__)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS data_layer_candles (
    "timestamp" TIMESTAMPTZ NOT NULL,
    symbol      TEXT NOT NULL,
    exchange    TEXT NOT NULL,
    timeframe   TEXT NOT NULL,
    open        DOUBLE PRECISION NOT NULL,
    high        DOUBLE PRECISION NOT NULL,
    low         DOUBLE PRECISION NOT NULL,
    close       DOUBLE PRECISION NOT NULL,
    volume      DOUBLE PRECISION NOT NULL,
    trades      INTEGER,
    PRIMARY KEY (symbol, exchange, timeframe, "timestamp")
);
"""

CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS ix_data_layer_candles_lookup
ON data_layer_candles (symbol, exchange, timeframe, "timestamp" DESC);
"""

TRY_HYPERTABLE_SQL = """
SELECT create_hypertable('data_layer_candles', 'timestamp',
    chunk_time_interval => INTERVAL '7 days', if_not_exists => TRUE);
"""

UPSERT_SQL = """
INSERT INTO data_layer_candles
    (symbol, exchange, timeframe, "timestamp", open, high, low, close, volume, trades)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
ON CONFLICT (symbol, exchange, timeframe, "timestamp")
DO UPDATE SET open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
              close = EXCLUDED.close, volume = EXCLUDED.volume, trades = EXCLUDED.trades;
"""


class PostgresStore:
    def __init__(self, database_url: Optional[str] = None):
        self._dsn = self._to_asyncpg_dsn(database_url or settings.DATABASE_URL)
        self._pool: Optional[asyncpg.Pool] = None

    @staticmethod
    def _to_asyncpg_dsn(url: str) -> str:
        # SQLAlchemy-style URLs may use postgresql+psycopg2://; asyncpg wants postgresql://
        if url.startswith("postgresql+psycopg2://"):
            return url.replace("postgresql+psycopg2://", "postgresql://", 1)
        return url

    async def connect(self):
        if self._pool is not None:
            return
        self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=5)
        await self._ensure_schema()

    async def _ensure_schema(self):
        async with self._pool.acquire() as conn:
            await conn.execute(CREATE_TABLE_SQL)
            await conn.execute(CREATE_INDEX_SQL)
            try:
                await conn.execute("CREATE EXTENSION IF NOT EXISTS timescaledb;")
                await conn.execute(TRY_HYPERTABLE_SQL)
                logger.info("data_layer_candles is a TimescaleDB hypertable")
            except Exception as e:
                logger.info(f"TimescaleDB not available, using plain table: {e}")

    async def close(self):
        if self._pool:
            await self._pool.close()

    async def get_last_timestamp(self, symbol: str, exchange: str, timeframe: str) -> Optional[datetime]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT max("timestamp") AS ts FROM data_layer_candles
                WHERE symbol = $1 AND exchange = $2 AND timeframe = $3
                """,
                symbol, exchange, timeframe,
            )
        ts = row["ts"] if row else None
        if ts is not None and ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts

    async def insert_candles(self, candles: List[Candle]):
        if not candles:
            return
        rows = [
            (c.symbol, c.exchange, c.timeframe, c.timestamp, c.open, c.high, c.low, c.close, c.volume, c.trades)
            for c in candles
        ]
        async with self._pool.acquire() as conn:
            await conn.executemany(UPSERT_SQL, rows)

    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: Optional[datetime] = None,
        exchange: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[dict]:
        end = end or datetime.now(timezone.utc)
        query = """
            SELECT "timestamp", symbol, exchange, timeframe, open, high, low, close, volume, trades
            FROM data_layer_candles
            WHERE symbol = $1 AND timeframe = $2 AND "timestamp" >= $3 AND "timestamp" <= $4
        """
        params = [symbol, timeframe, start, end]
        if exchange:
            query += " AND exchange = $5"
            params.append(exchange)
        query += ' ORDER BY "timestamp" ASC'
        if limit:
            query += f" LIMIT {int(limit)}"

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        return [dict(row) for row in rows]

"""
Backfill orchestration (___DataLayer.md section 7).

For each (symbol, timeframe): checks the last stored timestamp in Postgres,
fetches the missing range in batches of up to 1000 candles via REST
(respecting per-exchange concurrency limits), validates/normalizes, and
batch-inserts into Postgres + Redis.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import List

from app.data_layer.backfill.gap_detector import gap_start, timeframe_to_timedelta
from app.data_layer.core.config import settings
from app.data_layer.ingestion.sources.base import ExchangeSource
from app.data_layer.storage.postgres_store import PostgresStore
from app.data_layer.storage.redis_store import RedisStore

logger = logging.getLogger(__name__)

BATCH_SIZE = 1000


async def backfill_symbol_timeframe(
    source: ExchangeSource,
    pg: PostgresStore,
    redis: RedisStore,
    symbol: str,
    timeframe: str,
):
    last_ts = await pg.get_last_timestamp(symbol, source.name, timeframe)
    start = gap_start(last_ts, timeframe, settings.history_start)
    now = datetime.now(timezone.utc)

    if start >= now:
        return

    step = timeframe_to_timedelta(timeframe) * BATCH_SIZE
    total_inserted = 0

    while start < now:
        candles = await source.fetch_candles(symbol, timeframe, since=start, limit=BATCH_SIZE)
        if not candles:
            break

        await pg.insert_candles(candles)
        for candle in candles[-settings.DATALAYER_REDIS_CANDLE_LIMIT:]:
            await redis.add_candle(candle)

        total_inserted += len(candles)

        last_fetched = candles[-1].timestamp
        next_start = last_fetched + timeframe_to_timedelta(timeframe)
        if next_start <= start:
            # No progress (e.g. exchange returned <1 candle of new data); stop to avoid looping forever.
            break
        start = next_start

        if len(candles) < BATCH_SIZE:
            break

    if total_inserted:
        logger.info(f"Backfilled {total_inserted} candles for {symbol} {timeframe} ({source.name})")


async def run_backfill(source: ExchangeSource, pg: PostgresStore, redis: RedisStore, symbols: List[str], timeframes: List[str]):
    semaphore = asyncio.Semaphore(settings.DATALAYER_BACKFILL_CONCURRENCY)

    async def _task(symbol: str, timeframe: str):
        async with semaphore:
            try:
                await backfill_symbol_timeframe(source, pg, redis, symbol, timeframe)
            except Exception as e:
                logger.error(f"Backfill failed for {symbol} {timeframe}: {e}", exc_info=True)

    tasks = [
        _task(symbol, timeframe)
        for symbol in symbols
        for timeframe in timeframes
    ]
    await asyncio.gather(*tasks)
    logger.info(f"Backfill complete for {len(symbols)} symbols x {len(timeframes)} timeframes")

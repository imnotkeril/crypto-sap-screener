"""
Pipeline orchestration (___DataLayer.md section 12):

1. Load config
2. Connect to Redis and Postgres
3. Start WebSocket -> buffering mode
4. Run backfill for all symbols/timeframes in parallel
5. Backfill done -> flush WS buffer (closes the gap)
6. WS -> live mode
7. Indicators recomputed on every closed candle
8. (funding/OI polling: out of scope for v1)
9. Serving layer (Redis + Postgres) ready for the query API / FastAPI app
"""
import asyncio
import logging

from app.data_layer.backfill.backfill_manager import run_backfill
from app.data_layer.backfill.buffer import WsBuffer
from app.data_layer.core.config import settings
from app.data_layer.core.exceptions import StartupError
from app.data_layer.core.models import Candle, Ticker
from app.data_layer.ingestion.sources.binance import BinanceSource
from app.data_layer.processing.indicators import compute_indicators
from app.data_layer.serving.pubsub import PubSub
from app.data_layer.storage.postgres_store import PostgresStore
from app.data_layer.storage.redis_store import RedisStore

logger = logging.getLogger(__name__)


class DataLayerPipeline:
    def __init__(self):
        self.source = BinanceSource()
        self.redis = RedisStore()
        self.pg = PostgresStore()
        self.pubsub = PubSub()
        self.buffer = WsBuffer()

    async def start(self):
        logger.info("Starting data layer pipeline...")

        try:
            await self.redis.ping()
        except Exception as e:
            raise StartupError(f"Cannot connect to Redis: {e}")

        try:
            await self.pg.connect()
        except Exception as e:
            raise StartupError(f"Cannot connect to Postgres: {e}")

        symbols = settings.DATALAYER_SYMBOLS
        timeframes = settings.DATALAYER_TIMEFRAMES

        # Start WS streaming in buffering mode immediately.
        ws_task = asyncio.create_task(
            self.source.stream(symbols, timeframes, self._on_candle, self._on_ticker)
        )

        # Backfill history while WS messages are buffered.
        await run_backfill(self.source, self.pg, self.redis, symbols, timeframes)

        # Flush anything that arrived over WS while backfilling.
        buffered = await self.buffer.flush()
        logger.info(f"Flushing {len(buffered)} buffered WS messages, switching to live mode")
        for candle, is_closed in buffered:
            await self._process_candle(candle, is_closed)

        logger.info("Data layer pipeline is live")
        await ws_task

    async def _on_candle(self, candle: Candle, is_closed: bool):
        if await self.buffer.add(candle, is_closed):
            return
        await self._process_candle(candle, is_closed)

    async def _process_candle(self, candle: Candle, is_closed: bool):
        await self.redis.add_candle(candle)

        if not is_closed:
            return

        await self.pg.insert_candles([candle])
        await self.pubsub.publish_candle_closed(candle)

        try:
            recent = await self.redis.get_latest_candles(candle.exchange, candle.symbol, candle.timeframe, limit=250)
            indicators = compute_indicators(recent)
            if indicators:
                await self.redis.set_indicators(candle.symbol, candle.timeframe, indicators)
                await self.pubsub.publish_indicators(candle.symbol, candle.timeframe, indicators)
        except Exception as e:
            logger.warning(f"Indicator computation failed for {candle.symbol} {candle.timeframe}: {e}")

    async def _on_ticker(self, ticker: Ticker):
        await self.redis.set_ticker(ticker)
        await self.pubsub.publish_ticker(ticker)

    async def stop(self):
        await self.source.close()
        await self.redis.close()
        await self.pg.close()
        await self.pubsub.close()

"""
Binance data source: WebSocket streaming (combined kline + ticker streams)
and REST backfill of candles.

WS channels used (___DataLayer.md section 6):
  !ticker@arr            -> all 24h tickers at once
  <symbol>@kline_<tf>     -> candles

Binance allows up to 1024 streams per connection; we chunk conservatively.
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import List

from app.data_layer.core.config import settings
from app.data_layer.core.exceptions import NormalizationError
from app.data_layer.core.models import Candle
from app.data_layer.ingestion.rest_client import RestClient
from app.data_layer.ingestion.sources.base import ExchangeSource, OnCandle, OnTicker
from app.data_layer.ingestion.websocket_manager import WebSocketManager
from app.data_layer.normalization.normalizer import (
    normalize_kline_rest,
    normalize_kline_ws,
    normalize_ticker_ws,
)
from app.data_layer.normalization.symbol_mapper import to_exchange
from app.data_layer.normalization.validator import is_valid

logger = logging.getLogger(__name__)

STREAMS_PER_CONNECTION = 190  # conservative; Binance limit is 1024


class BinanceSource(ExchangeSource):
    name = "binance"

    def __init__(self):
        self._rest = RestClient(
            base_url=settings.BINANCE_REST_URL,
            max_concurrency=settings.DATALAYER_BACKFILL_CONCURRENCY,
        )
        self._managers: List[WebSocketManager] = []

    async def stream(self, symbols: List[str], timeframes: List[str], on_candle: OnCandle, on_ticker: OnTicker):
        tracked_symbols = {to_exchange(s).upper() for s in symbols}

        streams = ["!ticker@arr"]
        for symbol in symbols:
            exch_symbol = to_exchange(symbol).lower()
            for tf in timeframes:
                streams.append(f"{exch_symbol}@kline_{tf}")

        chunks = [streams[i:i + STREAMS_PER_CONNECTION] for i in range(0, len(streams), STREAMS_PER_CONNECTION)]

        async def handle_message(raw: str):
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("Received non-JSON WS message")
                return

            data = payload.get("data", payload)
            stream_name = payload.get("stream", "")

            event = data.get("e") if isinstance(data, dict) else None

            try:
                if event == "kline":
                    candle, is_closed = normalize_kline_ws(data, exchange=self.name)
                    if is_valid(candle):
                        await on_candle(candle, is_closed)
                elif stream_name == "!ticker@arr" and isinstance(data, list):
                    for item in data:
                        if item.get("s") not in tracked_symbols:
                            continue
                        ticker = normalize_ticker_ws(item, exchange=self.name)
                        if is_valid(ticker):
                            await on_ticker(ticker)
            except NormalizationError as e:
                logger.warning(f"Failed to normalize WS message: {e}")

        self._managers = []
        tasks = []
        for i, chunk in enumerate(chunks):
            url = f"{settings.BINANCE_WS_URL}/stream?streams={'/'.join(chunk)}"
            manager = WebSocketManager(
                url=url,
                on_message=handle_message,
                backoff_min=settings.DATALAYER_WS_BACKOFF_MIN,
                backoff_max=settings.DATALAYER_WS_BACKOFF_MAX,
                heartbeat_interval=settings.DATALAYER_WS_HEARTBEAT_INTERVAL,
                name=f"binance-ws-{i}",
            )
            self._managers.append(manager)
            tasks.append(asyncio.create_task(manager.run()))

        await asyncio.gather(*tasks)

    async def fetch_candles(self, symbol: str, timeframe: str, since: datetime, limit: int = 1000) -> List[Candle]:
        exch_symbol = to_exchange(symbol)
        response = await self._rest.get(
            "/api/v3/klines",
            params={
                "symbol": exch_symbol,
                "interval": timeframe,
                "startTime": int(since.timestamp() * 1000),
                "limit": limit,
            },
        )
        rows = response.json()

        candles = []
        for row in rows:
            try:
                candle = normalize_kline_rest(exch_symbol, timeframe, row, exchange=self.name)
            except NormalizationError as e:
                logger.warning(f"Failed to normalize REST kline row: {e}")
                continue
            if is_valid(candle):
                candles.append(candle)
        return candles

    async def close(self):
        for manager in self._managers:
            manager.stop()
        await self._rest.close()

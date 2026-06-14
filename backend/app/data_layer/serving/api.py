"""
HTTP serving layer for the Market Data Layer.

Runs the ingestion pipeline (WebSocket + backfill) as a background task and
exposes the query API over HTTP so other services (the Vercel screener,
terminal, backtester) can read candles/tickers/indicators without talking to
Redis/Postgres directly.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Query

from app.data_layer.core.config import settings
from app.data_layer.core.pipeline import DataLayerPipeline
from app.data_layer.serving.query_api import QueryAPI

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    pipeline = DataLayerPipeline()
    app.state.pipeline = pipeline
    app.state.query_api = QueryAPI(pipeline.pg, pipeline.redis)

    await pipeline.redis.ping()
    await pipeline.pg.connect()

    pipeline_task = asyncio.create_task(pipeline.start())

    try:
        yield
    finally:
        pipeline_task.cancel()
        try:
            await pipeline_task
        except (asyncio.CancelledError, Exception):
            pass
        await pipeline.stop()


app = FastAPI(title="Market Data Layer", lifespan=lifespan)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "exchange": settings.EXCHANGE,
        "symbols": settings.DATALAYER_SYMBOLS,
        "timeframes": settings.DATALAYER_TIMEFRAMES,
    }


@app.get("/ticker")
async def get_ticker(symbol: str):
    ticker = await app.state.query_api.get_ticker(symbol)
    if ticker is None:
        raise HTTPException(status_code=404, detail=f"No ticker for {symbol}")
    return ticker


@app.get("/candles/latest")
async def get_latest_candles(symbol: str, timeframe: str, limit: int = Query(default=100, le=500)):
    return await app.state.query_api.get_latest_candles(symbol, timeframe, limit)


@app.get("/candles")
async def get_candles(
    symbol: str,
    timeframe: str,
    start: datetime,
    end: Optional[datetime] = None,
    limit: Optional[int] = Query(default=None, le=10000),
):
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end is not None and end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return await app.state.query_api.get_candles(symbol, timeframe, start, end, limit=limit)


@app.get("/indicators")
async def get_indicators(symbol: str, timeframe: str):
    return await app.state.query_api.get_indicators(symbol, timeframe)

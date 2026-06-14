"""
Configuration for the Market Data Layer service.

Loaded from environment variables (and .env). Lists are accepted as
comma-separated strings, e.g.:

    DATALAYER_SYMBOLS=BTC/USDT,ETH/USDT,SOL/USDT
    DATALAYER_TIMEFRAMES=1m,5m,15m,1h,4h,1d
"""
from datetime import datetime, timezone
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings


def _split_csv(v):
    if isinstance(v, str):
        return [item.strip() for item in v.split(",") if item.strip()]
    return v


class DataLayerSettings(BaseSettings):
    """Settings for the standalone data layer worker."""

    # Exchange (v1: binance only)
    EXCHANGE: str = "binance"

    # Symbols to track, normalized form (BTC/USDT)
    DATALAYER_SYMBOLS: List[str] = [
        "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
    ]

    # Timeframes for candles / indicators
    DATALAYER_TIMEFRAMES: List[str] = ["1m", "5m", "15m", "1h", "4h", "1d"]

    # Backfill depth if no history exists yet
    DATALAYER_HISTORY_START: str = "2023-01-01"

    # Max candles kept per (symbol, timeframe) in Redis sorted sets
    DATALAYER_REDIS_CANDLE_LIMIT: int = 500

    # TTLs (seconds)
    DATALAYER_TICKER_TTL: int = 10

    # Storage
    REDIS_URL: str = "redis://localhost:6379"
    DATABASE_URL: str = "sqlite:///./data/stat_arb.db"

    # Binance REST
    BINANCE_REST_URL: str = "https://api.binance.com"
    BINANCE_WS_URL: str = "wss://stream.binance.com:9443"

    # Rate limit: max parallel REST backfill requests per exchange
    DATALAYER_BACKFILL_CONCURRENCY: int = 10

    # WebSocket reconnect backoff (seconds)
    DATALAYER_WS_BACKOFF_MIN: float = 1.0
    DATALAYER_WS_BACKOFF_MAX: float = 60.0
    DATALAYER_WS_HEARTBEAT_INTERVAL: float = 20.0

    # Funding/OI polling interval (not implemented in v1, reserved)
    DATALAYER_FUNDING_POLL_INTERVAL: int = 300

    @field_validator("DATALAYER_SYMBOLS", "DATALAYER_TIMEFRAMES", mode="before")
    @classmethod
    def _parse_csv_lists(cls, v):
        return _split_csv(v)

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def _strip_database_url(cls, v):
        if isinstance(v, str):
            return v.strip()
        return v

    @property
    def history_start(self) -> datetime:
        return datetime.strptime(self.DATALAYER_HISTORY_START, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = DataLayerSettings()

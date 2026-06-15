"""
Normalized data models shared across ingestion, storage and serving.

Field names/semantics follow ___DataLayer.md section 4. Only Candle and
Ticker are implemented in v1 (Binance-only, candles + ticker scope).
"""
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Candle:
    symbol: str            # Normalized: BTC/USDT
    exchange: str          # binance
    timeframe: str         # 1m | 5m | 15m | 1h | 4h | 1d
    timestamp: datetime    # UTC, candle open time
    open: float
    high: float
    low: float
    close: float
    volume: float
    trades: Optional[int] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["timestamp"] = self.timestamp.astimezone(timezone.utc).isoformat()
        return d


@dataclass
class Ticker:
    symbol: str
    exchange: str
    timestamp: datetime
    last: float
    bid: float
    ask: float
    volume_24h: float
    change_24h: float      # percent
    high_24h: float
    low_24h: float

    def to_dict(self) -> dict:
        d = asdict(self)
        d["timestamp"] = self.timestamp.astimezone(timezone.utc).isoformat()
        return d

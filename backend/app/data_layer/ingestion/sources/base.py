"""Abstract base class for exchange data sources."""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Awaitable, Callable, List

from app.data_layer.core.models import Candle, Ticker

OnCandle = Callable[[Candle, bool], Awaitable[None]]  # (candle, is_closed)
OnTicker = Callable[[Ticker], Awaitable[None]]


class ExchangeSource(ABC):
    """Common interface implemented by each exchange (binance, bybit, okx, ...)."""

    name: str

    @abstractmethod
    async def stream(self, symbols: List[str], timeframes: List[str], on_candle: OnCandle, on_ticker: OnTicker):
        """Connect to the exchange WebSocket(s) and stream candles/tickers until cancelled."""

    @abstractmethod
    async def fetch_candles(self, symbol: str, timeframe: str, since: datetime, limit: int = 1000) -> List[Candle]:
        """Fetch historical candles via REST, starting from `since` (inclusive)."""

    @abstractmethod
    async def close(self):
        """Release any open connections/resources."""

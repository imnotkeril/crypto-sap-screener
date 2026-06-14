"""
Normalization of raw Binance payloads (WebSocket + REST) into the unified
Candle / Ticker models.
"""
from datetime import datetime, timezone
from typing import Tuple

from app.data_layer.core.exceptions import NormalizationError
from app.data_layer.core.models import Candle, Ticker
from app.data_layer.normalization.symbol_mapper import to_unified


def _ms_to_dt(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def normalize_kline_ws(msg: dict, exchange: str = "binance") -> Tuple[Candle, bool]:
    """Normalize a Binance `<symbol>@kline_<tf>` WS message.

    Returns (candle, is_closed).
    """
    try:
        k = msg["k"]
        candle = Candle(
            symbol=to_unified(k["s"]),
            exchange=exchange,
            timeframe=k["i"],
            timestamp=_ms_to_dt(k["t"]),
            open=float(k["o"]),
            high=float(k["h"]),
            low=float(k["l"]),
            close=float(k["c"]),
            volume=float(k["v"]),
            trades=int(k.get("n")) if k.get("n") is not None else None,
        )
        return candle, bool(k.get("x", False))
    except (KeyError, ValueError, TypeError) as e:
        raise NormalizationError(f"Could not normalize kline WS message: {e}")


def normalize_kline_rest(symbol: str, timeframe: str, row: list, exchange: str = "binance") -> Candle:
    """Normalize one row of a Binance REST `/api/v3/klines` response."""
    try:
        return Candle(
            symbol=to_unified(symbol),
            exchange=exchange,
            timeframe=timeframe,
            timestamp=_ms_to_dt(int(row[0])),
            open=float(row[1]),
            high=float(row[2]),
            low=float(row[3]),
            close=float(row[4]),
            volume=float(row[5]),
            trades=int(row[8]) if len(row) > 8 and row[8] is not None else None,
        )
    except (IndexError, ValueError, TypeError) as e:
        raise NormalizationError(f"Could not normalize REST kline row: {e}")


def normalize_ticker_ws(msg: dict, exchange: str = "binance") -> Ticker:
    """Normalize one entry of a Binance `!ticker@arr` WS message."""
    try:
        return Ticker(
            symbol=to_unified(msg["s"]),
            exchange=exchange,
            timestamp=_ms_to_dt(int(msg["E"])),
            last=float(msg["c"]),
            bid=float(msg["b"]),
            ask=float(msg["a"]),
            volume_24h=float(msg["v"]),
            change_24h=float(msg["P"]),
            high_24h=float(msg["h"]),
            low_24h=float(msg["l"]),
        )
    except (KeyError, ValueError, TypeError) as e:
        raise NormalizationError(f"Could not normalize ticker WS message: {e}")

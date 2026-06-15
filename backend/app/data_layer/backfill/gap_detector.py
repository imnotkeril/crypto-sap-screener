"""
Determine the time range that needs to be (re)fetched for a given
(symbol, exchange, timeframe), per ___DataLayer.md section 7:

  - If no history exists -> backfill from the configured start_date
  - If history exists -> only fetch the gap (last_timestamp -> now)
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

_TIMEFRAME_SECONDS = {
    "1m": 60,
    "5m": 5 * 60,
    "15m": 15 * 60,
    "1h": 60 * 60,
    "4h": 4 * 60 * 60,
    "1d": 24 * 60 * 60,
}


def timeframe_to_timedelta(timeframe: str) -> timedelta:
    if timeframe not in _TIMEFRAME_SECONDS:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    return timedelta(seconds=_TIMEFRAME_SECONDS[timeframe])


def gap_start(last_timestamp: Optional[datetime], timeframe: str, history_start: datetime) -> datetime:
    """Return the timestamp to start fetching from."""
    if last_timestamp is None:
        return history_start

    # Resume from the candle right after the last one we have.
    return last_timestamp + timeframe_to_timedelta(timeframe)


def has_gap(last_timestamp: Optional[datetime], timeframe: str, now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(timezone.utc)
    if last_timestamp is None:
        return True
    return (now - last_timestamp) > timeframe_to_timedelta(timeframe)

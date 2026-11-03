"""R-10: cached prices must expire once a newer closed candle exists."""
import pandas as pd

from app.modules.screener.data_loader import is_series_fresh, TIMEFRAME_MS

DAY = TIMEFRAME_MS['1d']


def _series(last_open_ms):
    idx = pd.to_datetime([last_open_ms - DAY, last_open_ms], unit='ms')
    return pd.Series([1.0, 2.0], index=idx)


def test_fresh_when_last_closed_bar_present():
    now = 10 * DAY + 3600_000          # 1h into day 10 -> last closed bar opens at day 9
    assert is_series_fresh(_series(9 * DAY), '1d', now_ms=now)


def test_stale_when_a_closed_bar_is_missing():
    now = 10 * DAY + 3600_000
    assert not is_series_fresh(_series(8 * DAY), '1d', now_ms=now)


def test_empty_is_stale():
    assert not is_series_fresh(pd.Series(dtype=float), '1d')


def test_intraday_goes_stale_within_hours():
    h = TIMEFRAME_MS['1h']
    assert not is_series_fresh(_series(5 * h), '1h', now_ms=9 * h + 1)

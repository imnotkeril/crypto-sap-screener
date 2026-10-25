"""Stale / empty / failing market-data behaviour of the intraday monitor."""
import numpy as np
import pandas as pd
import pytest

from app.modules.screener import intraday_monitor as im


class Screener:
    def get_results(self):
        return [{"id": 1, "asset_a": "AAA", "asset_b": "BBB", "composite_score": 90, "current_zscore": 0.5}]


def _frame(start, n=864, seed=0):
    rng = np.random.default_rng(seed)
    base = 100 + np.cumsum(rng.normal(size=n))
    idx = pd.date_range(start, periods=n, freq="5min")
    return base, idx


class Loader:
    def __init__(self, start="2026-01-01", mode="ok"):
        self.start, self.mode = start, mode

    def fetch_ohlcv(self, asset, days=1, db=None, timeframe="5m"):
        if self.mode == "raise":
            raise ConnectionError("exchange down")
        if self.mode == "none":
            return None
        if self.mode == "empty":
            return pd.DataFrame({"close": []})
        base, idx = _frame(self.start)
        close = base if asset == "BBB" else 1.5 * base + np.random.default_rng(1).normal(scale=0.3, size=len(base))
        return pd.DataFrame({"close": close}, index=idx)


@pytest.fixture()
def mon(monkeypatch):
    monkeypatch.setattr(im, "get_live_screener", lambda: Screener())
    monkeypatch.setattr(im, "SessionLocal", None)
    return im.IntradayMonitor()


@pytest.mark.parametrize("mode", ["none", "empty"])
def test_empty_feed_is_skipped_not_crash(mon, mode):
    mon.data_loader = Loader(mode=mode)
    s = mon.get_snapshot()
    assert s["pairs"] == [] and s["skipped_pairs"] == 1 and s["last_error"] is None


def test_exchange_error_is_swallowed_and_flagged(mon):
    mon.data_loader = Loader(mode="raise")
    s = mon.get_snapshot()
    # fetch error is caught per pair -> skipped (pair-level), request still succeeds
    assert s["pairs"] == [] and s["skipped_pairs"] + (1 if s["last_error"] else 0) >= 1


def test_failure_keeps_previous_snapshot_and_reports_error(mon, monkeypatch):
    mon.data_loader = Loader()
    first = mon.get_snapshot()
    assert len(first["pairs"]) == 1
    mon.last_update = None                      # force a refresh
    monkeypatch.setattr(mon, "_update", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    s = mon.get_snapshot()
    assert s["last_error"] and len(s["pairs"]) == 1          # previous data still served, error surfaced
    assert "boom" not in s["last_error"]                     # no internal detail leaked


def test_no_daily_results_returns_empty_without_marking_fresh(monkeypatch):
    class Nothing:
        def get_results(self):
            return []
    monkeypatch.setattr(im, "get_live_screener", lambda: Nothing())
    m = im.IntradayMonitor()
    s = m.get_snapshot()
    assert s["pairs"] == [] and s["last_update"] is None


@pytest.mark.xfail(strict=True, reason="BUG-7: monitor never checks candle timestamps; a feed whose last candle is "
                                       "months old yields a snapshot stamped updated_at=now with is_unusual "
                                       "signals (intraday_monitor.py _update, ~line 160-200)")
def test_stale_candles_are_rejected(mon):
    mon.data_loader = Loader(start="2026-01-01")   # last candle ~3 days after 2026-01-01, today is 2026-10-25
    s = mon.get_snapshot()
    assert s["pairs"] == []

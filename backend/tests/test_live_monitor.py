import numpy as np
import pandas as pd

from app.modules.screener import intraday_monitor as im


class FakeScreener:
    def get_results(self):
        return [{"id": 1, "asset_a": "AAA", "asset_b": "BBB", "composite_score": 90, "current_zscore": 0.5}]


class FakeLoader:
    calls = 0

    def fetch_ohlcv(self, asset, days=1, db=None, timeframe="5m"):
        FakeLoader.calls += 1
        n = 864
        rng = np.random.default_rng(0)
        base = 100 + np.cumsum(rng.normal(size=n))
        close = base if asset == "BBB" else 1.5 * base + rng.normal(scale=0.3, size=n)
        idx = pd.date_range("2026-01-01", periods=n, freq="5min")
        return pd.DataFrame({"close": close}, index=idx)


def test_snapshot_uses_fresh_candles_and_caches(monkeypatch):
    monkeypatch.setattr(im, "get_live_screener", lambda: FakeScreener())
    mon = im.IntradayMonitor()
    mon.data_loader = FakeLoader()
    snap = mon.get_snapshot()
    assert len(snap["pairs"]) == 1 and snap["last_error"] is None
    p = snap["pairs"][0]
    assert abs(p["beta"] - 1.5) < 0.3
    calls = FakeLoader.calls
    mon.get_snapshot()  # within interval -> served from cache
    assert FakeLoader.calls == calls


def test_snapshot_reports_skipped_pairs(monkeypatch):
    class Short(FakeLoader):
        def fetch_ohlcv(self, *a, **k):
            return pd.DataFrame({"close": [1.0, 2.0]})

    monkeypatch.setattr(im, "get_live_screener", lambda: FakeScreener())
    mon = im.IntradayMonitor()
    mon.data_loader = Short()
    snap = mon.get_snapshot()
    assert snap["pairs"] == [] and snap["skipped_pairs"] == 1

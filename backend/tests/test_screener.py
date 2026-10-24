import numpy as np
import pandas as pd
import pytest

from app.modules.screener.screener import PairsScreener
from app.modules.shared.models import ScreeningConfig

N = 400


class FakeLoader:
    def __init__(self, series):
        self.series = series

    def get_price_series(self, asset, days=None, db=None, timeframe="1d"):
        return self.series[asset]


def _ou(n, seed, theta=0.3):
    rng = np.random.default_rng(seed)
    x = np.zeros(n)
    for t in range(1, n):
        x[t] = (1 - theta) * x[t - 1] + rng.normal()
    return x


def _universe(n_noise=6):
    idx = pd.date_range("2024-01-01", periods=N, freq="D")
    rng = np.random.default_rng(0)
    base = 100 + np.cumsum(rng.normal(size=N) * 5)
    series = {"AAA": pd.Series(base, idx), "BBB": pd.Series(10 + 0.5 * base + _ou(N, 1), idx)}
    for i in range(n_noise):
        # random walks with a common factor so correlation passes the pre-filter
        series[f"N{i}"] = pd.Series(base * (0.8 + 0.05 * i) + np.cumsum(rng.normal(size=N) * 2) , idx)
    return series


def _screener(series):
    s = PairsScreener(db=None)
    s.data_loader = FakeLoader(series)
    return s


def _cfg(**kw):
    base = dict(assets=None, lookback_days=N, min_correlation=0.7, max_adf_pvalue=0.05,
                include_hurst=True, min_half_life=1.0)
    base.update(kw)
    return ScreeningConfig(**base)


def test_net_edge_arithmetic():
    series = _universe(0)
    s = _screener(series)
    cfg = _cfg(taker_fee_bps=5, slippage_bps=2, funding_bps_per_8h=1, entry_zscore=2.0)
    r = s._test_pair("AAA", "BBB", cfg)
    assert r is not None
    gross = 2.0 * r["spread_std"]
    fees = 4 * (5 + 2) * 0.01  # 0.28 %
    funding = (r["half_life"] * 24 / 8) * 1 * 0.01
    assert r["expected_net_edge_pct"] == pytest.approx(gross - fees - funding, rel=1e-9)


def test_net_edge_penalises_costs_in_score():
    s = _screener(_universe(0))
    cheap = s._test_pair("AAA", "BBB", _cfg(taker_fee_bps=0, slippage_bps=0, funding_bps_per_8h=0))
    pricey = s._test_pair("AAA", "BBB", _cfg(taker_fee_bps=500, slippage_bps=500))
    assert cheap["expected_net_edge_pct"] > pricey["expected_net_edge_pct"]
    assert cheap["composite_score"] > pricey["composite_score"]


def test_hurst_score_rewards_mean_reversion():
    s = _screener(_universe(0))
    r = s._test_pair("AAA", "BBB", _cfg())
    assert r["hurst_exponent"] is not None and r["hurst_exponent"] < 0.5


def test_screen_finds_planted_pair_and_fdr_is_stricter():
    series = _universe(6)
    cfg = _cfg(assets=list(series), use_fdr=True)
    with_fdr = _screener(series).screen_pairs(cfg)
    names = {(r["asset_a"], r["asset_b"]) for r in with_fdr}
    assert ("AAA", "BBB") in names
    raw = _screener(series).screen_pairs(_cfg(assets=list(series), use_fdr=False))
    assert len(with_fdr) <= len(raw)
    for r in with_fdr:
        assert r["adf_pvalue_fdr"] >= r["adf_pvalue"]

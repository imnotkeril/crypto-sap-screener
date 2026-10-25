import numpy as np
import pandas as pd

from app.modules.screener.cointegration import CointegrationTester
from app.modules.screener.hurst import HurstCalculator
from app.modules.screener.kalman import KalmanHedge


def _walk(n=500, seed=0):
    return np.cumsum(np.random.default_rng(seed).normal(size=n))


def _ou(n=500, theta=0.3, seed=1):
    rng = np.random.default_rng(seed)
    x = np.zeros(n)
    for t in range(1, n):
        x[t] = (1 - theta) * x[t - 1] + rng.normal()
    return x


def test_hurst_random_walk_near_half():
    h = HurstCalculator.generalized_hurst_exponent(pd.Series(_walk(2000)))
    assert 0.35 < h < 0.65


def test_hurst_mean_reverting_below_random_walk():
    h_ou = HurstCalculator.generalized_hurst_exponent(pd.Series(_ou(2000)))
    h_rw = HurstCalculator.generalized_hurst_exponent(pd.Series(_walk(2000)))
    assert h_ou < h_rw and h_ou < 0.5


def test_hurst_too_short_returns_none():
    assert HurstCalculator.generalized_hurst_exponent(pd.Series(_walk(20))) is None


def _pair(scale=1.0, n=400, true_beta=1.5, seed=3):
    rng = np.random.default_rng(seed)
    b = 100 + np.cumsum(rng.normal(size=n))
    a = (10 + true_beta * b + _ou(n, seed=seed)) * scale
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.Series(a, idx), pd.Series(b, idx)


def test_engle_granger_detects_and_recovers_beta():
    a, b = _pair()
    is_coint, beta, _, p, _ = CointegrationTester.engle_granger_test(a, b)
    assert is_coint and p < 0.05
    assert abs(beta - 1.5) < 0.1


def test_beta_is_price_unit_ratio_not_a_bug():
    """Beta is the hedge ratio in units of B per unit of A, so it scales with
    the price ratio of the two assets (e.g. ~544 DOGE per SOL)."""
    a, b = _pair(scale=1.0)
    _, beta1, *_ = CointegrationTester.engle_granger_test(a, b)
    _, beta2, *_ = CointegrationTester.engle_granger_test(a * 100, b)
    assert abs(beta2 / beta1 - 100) < 1


def test_unrelated_walks_not_cointegrated():
    idx = pd.date_range("2024-01-01", periods=400)
    a = pd.Series(100 + _walk(400, 10), idx)
    b = pd.Series(100 + _walk(400, 11), idx)
    _, _, _, p, _ = CointegrationTester.engle_granger_test(a, b)
    assert p > 0.05


def test_half_life_ou():
    hl = CointegrationTester.half_life(pd.Series(_ou(2000, theta=0.2)))
    assert hl is not None and 2.0 < hl < 5.0  # ln2/0.2 = 3.47


def test_half_life_random_walk_none_or_long():
    hl = CointegrationTester.half_life(pd.Series(_walk(500, 5)))
    assert hl is None or hl > 20


def test_kalman_tracks_drifting_beta():
    n = 600
    rng = np.random.default_rng(7)
    b = 100 + np.cumsum(rng.normal(size=n))
    true_beta = np.linspace(1.2, 1.8, n)
    a = true_beta * b + rng.normal(scale=0.2, size=n)
    out = KalmanHedge().run(pd.Series(a), pd.Series(b))
    assert abs(out["beta"].iloc[-1] - 1.8) < 0.15
    assert np.isfinite(out["zscore"].iloc[-50:]).all()


def test_kalman_empty_input():
    assert KalmanHedge().run(pd.Series(dtype=float), pd.Series(dtype=float)).empty

"""R-03: Kalman z-scores must not depend on the price level."""
import numpy as np
import pandas as pd

from app.modules.screener.kalman import KalmanHedge


def _pair(n=400, seed=3):
    rng = np.random.default_rng(seed)
    b = 100 + np.cumsum(rng.normal(size=n))
    a = 1.5 * b + rng.normal(scale=0.5, size=n)
    return pd.Series(a), pd.Series(b)


def test_zscore_invariant_to_price_scale():
    a, b = _pair()
    base = KalmanHedge().run(a, b)["zscore"].to_numpy()
    for k in (1e-4, 1e3):
        z = KalmanHedge().run(a * k, b)["zscore"].to_numpy()
        assert np.allclose(z, base, atol=1e-6)
        z2 = KalmanHedge().run(a * k, b * k)["zscore"].to_numpy()
        assert np.allclose(z2, base, atol=1e-6)


def test_beta_and_spread_stay_in_price_units():
    a, b = _pair()
    out = KalmanHedge().run(a * 1000, b)
    assert abs(out["beta"].iloc[-1] - 1500) < 150           # beta scales with a's units
    assert abs(out["spread"].iloc[-50:]).mean() > 100 * abs(KalmanHedge().run(a, b)["spread"].iloc[-50:]).mean() / 2


def test_planted_shock_not_exploding_for_high_priced_leg():
    a, b = _pair()
    a = a * 1000
    a.iloc[-1] += 10 * (a.diff().std())
    z = KalmanHedge().run(a, b)["zscore"]
    assert abs(z.iloc[-1]) < 30

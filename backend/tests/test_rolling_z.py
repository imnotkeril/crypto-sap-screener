"""R-02: rolling-z window must be wide enough for a planted shock to reach the entry z."""
import numpy as np
import pandas as pd

from app.modules.screener.cointegration import CointegrationTester, rolling_z_window


def test_window_floor_and_cap():
    assert rolling_z_window(2, 300) == 20          # floor
    assert rolling_z_window(10, 300) == 30         # 3 x half-life
    assert rolling_z_window(200, 100) == 50        # capped at half the sample
    assert rolling_z_window(3, 10) == 10           # never above the sample


def test_planted_shock_reaches_entry_threshold_for_fast_pairs():
    rng = np.random.default_rng(0)
    base = rng.normal(0, 1, 300)
    base[-1] = 8.0                                  # planted shock on the last bar
    spread = pd.Series(base)
    z = CointegrationTester().rolling_zscore(spread, rolling_z_window(2.0, len(spread)))
    assert z.iloc[-1] > 3.0
    # the old 5-bar window is mathematically capped at (w-1)/sqrt(w) = 1.79
    z_old = CointegrationTester().rolling_zscore(spread, 5)
    assert z_old.iloc[-1] < 1.8

"""Backtester on synthetic data (no network): accounting invariants + metric reconciliation."""
import numpy as np
import pandas as pd
import pytest

from app.modules.backtester.backtester import Backtester
from app.modules.backtester.strategy import ZScoreStrategy, TradeSignal


def _series(n=300, seed=1):
    rng = np.random.default_rng(seed)
    b = 100 + np.cumsum(rng.normal(size=n))
    a = 2 * b + rng.normal(scale=2, size=n)
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    return pd.Series(a, index=idx), pd.Series(b, index=idx)


class DL:
    def __init__(self, a, b):
        self.a, self.b = a, b
        self.timeframes = []

    def get_price_series(self, symbol, days=0, db=None, timeframe="1d"):
        self.timeframes.append(timeframe)
        return self.a if symbol == "A" else self.b


def _run(tc=0.0, n=300, capital=10000.0, **strat):
    a, b = _series(n)
    bt = Backtester(capital, tc)
    bt.data_loader = DL(a, b)
    s = ZScoreStrategy(entry_threshold=2.0, take_profit=0.0, take_profit_type="zscore", **strat)
    return bt.run_backtest("A", "B", s, lookback_days=n, position_size_pct=100.0)


def test_backtest_is_deterministic_and_produces_trades():
    r1, r2 = _run(), _run()
    assert len(r1["trades"]) >= 5
    assert [t["pnl"] for t in r1["trades"]] == [t["pnl"] for t in r2["trades"]]
    assert r1["beta"] == pytest.approx(2.0, abs=0.15)  # planted hedge ratio


def test_zero_cost_trade_pnl_equals_leg_pnl_sum():
    r = _run(tc=0.0)
    for t in r["trades"]:
        assert t["pnl"] == pytest.approx(t["pnl_a"] + t["pnl_b"], abs=1e-6)
        # short_spread = short A / long B; golden leg check from entry/exit prices
        sign = -1 if t["entry_signal"] == "short_spread" else 1
        assert t["pnl_a"] == pytest.approx(sign * (t["exit_price_a"] - t["entry_price_a"]) * t["quantity_a"], rel=1e-6)
        assert t["pnl_b"] == pytest.approx(-sign * (t["exit_price_b"] - t["entry_price_b"]) * t["quantity_b"], rel=1e-6)


def test_zero_cost_equity_reconciles_with_closed_trade_pnl():
    r = _run(tc=0.0)
    closed = [t for t in r["trades"] if t.get("pnl") is not None]
    assert r["equity_curve"][0] == pytest.approx(10000.0)
    assert r["equity_curve"][-1] == pytest.approx(10000.0 + sum(t["pnl"] for t in closed), rel=1e-6)
    assert len(r["equity_curve"]) == len(r["equity_dates"])


def test_costs_reduce_final_equity_by_expected_amount():
    free, paid = _run(tc=0.0), _run(tc=0.001)
    assert [t["entry_date"] for t in free["trades"]] == [t["entry_date"] for t in paid["trades"]]
    assert paid["equity_curve"][-1] < free["equity_curve"][-1]
    # each closed trade pays an exit cost: pnl_paid = pnl_free - 0.001*(entry notional)
    t0, t1 = free["trades"][0], paid["trades"][0]
    # BUG-8 fixed: exit cost is charged on the exit-price notional.
    exit_notional = abs(t1["quantity_a"]) * t1["exit_price_a"] + abs(t1["quantity_b"]) * t1["exit_price_b"]
    assert t0["pnl"] - t1["pnl"] == pytest.approx(0.001 * exit_notional, rel=1e-9)


def test_backtest_passes_pair_timeframe_to_loader():
    a, b = _series(300)
    bt = Backtester()
    bt.data_loader = DL(a, b)
    bt.run_backtest("A", "B", ZScoreStrategy(), lookback_days=300, timeframe="1h")
    assert set(bt.data_loader.timeframes) == {"1h"}


def test_metrics_block_matches_trades():
    r = _run(tc=0.001)
    m = r["metrics"]
    closed = [t for t in r["trades"] if t.get("pnl") is not None]
    wins = sum(1 for t in closed if t["pnl"] > 0)
    key = next(k for k in m if "win_rate" in k)
    assert m[key] == pytest.approx(100.0 * wins / len(closed), abs=1e-6)
    ec = pd.Series(r["equity_curve"])
    dd = next((k for k in m if k in ("max_drawdown", "max_drawdown_pct")), None)
    if dd:
        assert m[dd] == pytest.approx(abs(((ec - ec.cummax()) / ec.cummax()).min()) * 100, rel=1e-3, abs=1e-6)


def test_insufficient_data_raises():
    a, b = _series(40)
    bt = Backtester()
    bt.data_loader = DL(a, b)
    with pytest.raises(ValueError):
        bt.run_backtest("A", "B", ZScoreStrategy(), lookback_days=40)


def test_signals_entry_boundaries():
    z = pd.Series([0.0, 1.99, 2.0, -2.0, -1.99, float("nan")])
    sig = ZScoreStrategy(entry_threshold=2.0).generate_signals(z)
    assert list(sig) == [TradeSignal.HOLD, TradeSignal.HOLD, TradeSignal.SHORT_SPREAD,
                         TradeSignal.LONG_SPREAD, TradeSignal.HOLD, TradeSignal.HOLD]


def test_backtest_api_rejects_out_of_range_params(client, auth):
    for body in ({"asset_a": "A", "asset_b": "B", "entry_threshold": 0.1},
                 {"asset_a": "A", "asset_b": "B", "lookback_days": 10},
                 {"asset_a": "A", "asset_b": "B", "initial_capital": 0},
                 {"asset_a": "A", "asset_b": "B", "stop_loss_type": "bogus"}):
        assert client.post("/api/v1/backtester/run", json=body, headers=auth).status_code == 422


# ---- P1 regressions: R-07 (no future beta), R-08 (stop side), R-09 (next-bar fill) ---------------
def test_no_trades_before_trailing_window_is_available():
    """R-07: with <30 trailing bars there is no beta; the bar is skipped, not fitted on the future."""
    r = _run()
    first = pd.Timestamp(r["trades"][0]["entry_date"])
    a, _ = _series()
    assert first > a.index[30]


def test_entries_fill_one_bar_after_signal_close():
    """R-09: entry price is the NEXT bar's close, not the close the z-score was computed on."""
    a, b = _series()
    r = _run()
    t = r["trades"][0]
    d = pd.Timestamp(t["entry_date"])
    assert t["entry_price_a"] == pytest.approx(float(a.loc[d]))
    assert d > a.index[31]


def _persistent_run(seed, **strat):
    """AR(1) spread so z persists across bars (white-noise spreads make next-bar z independent)."""
    rng = np.random.default_rng(seed)
    n = 500
    b = 100 + np.cumsum(rng.normal(size=n))
    sp = np.zeros(n)
    for i in range(1, n):
        sp[i] = 0.93 * sp[i - 1] + rng.normal(scale=1.0)
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    bt = Backtester(10000.0, 0.0)
    bt.data_loader = DL(pd.Series(2 * b + sp, index=idx), pd.Series(b, index=idx))
    s = ZScoreStrategy(entry_threshold=2.0, take_profit=0.0, take_profit_type="zscore", **strat)
    return bt.run_backtest("A", "B", s, lookback_days=n, position_size_pct=100.0)


def test_z_stop_triggers_on_adverse_side_only():
    """R-08: a z-score stop fires when z moves FURTHER against the entry side, never on recovery."""
    stops = []
    for seed in range(8):
        stops += [t for t in _persistent_run(seed, stop_loss=3.0, stop_loss_type="zscore")["trades"]
                  if t["exit_reason"] == "stop_loss"]
    assert stops, "expected at least one adverse-move stop on persistent spreads"
    for t in stops:
        if t["entry_signal"] == "long_spread":     # entered at z <= -entry; adverse = lower z
            assert t["exit_zscore"] <= -3.0
        else:
            assert t["exit_zscore"] >= 3.0

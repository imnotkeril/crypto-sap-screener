"""Golden checks: position calculator, backtest metrics, history analyzer (hand-computed)."""
import math

import pandas as pd
import pytest

from app.modules.backtester.metrics import BacktestMetrics as M
from app.modules.calculator.position_calculator import PositionCalculator as C, PositionStrategy as S
from app.modules.history.history_analyzer import HistoryAnalyzer as H


# ---- position calculator -------------------------------------------------
def test_dollar_neutral_negative_z_long_spread():
    # capital 1000, beta 0.5, pa=100, pb=50, z=-2 -> long A $1000 (10 units), short B $500 (10 units)
    p = C.calculate_position(1000, 0.5, 100, 50, S.DOLLAR_NEUTRAL, zscore=-2)
    assert p["asset_a"] == {"side": "long", "quantity": 10.0, "dollar_amount": 1000, "price": 100}
    assert p["asset_b"] == {"side": "short", "quantity": 10.0, "dollar_amount": 500.0, "price": 50}
    assert p["net_exposure"] == 500.0


def test_dollar_neutral_positive_z_short_spread():
    p = C.calculate_position(1000, 2.0, 10, 4, S.DOLLAR_NEUTRAL, zscore=1.5)
    assert p["asset_a"]["side"] == "short" and p["asset_b"]["side"] == "long"
    assert p["asset_a"]["quantity"] == 100.0 and p["asset_b"]["quantity"] == 500.0  # 2000/4


def test_zero_zscore_defaults_to_long_spread():
    p = C.calculate_position(100, 1, 1, 1, zscore=0)
    assert (p["asset_a"]["side"], p["asset_b"]["side"]) == ("long", "short")


def test_equal_dollar_halves_capital():
    p = C.calculate_position(1000, 0.5, 100, 50, S.EQUAL_DOLLAR, zscore=-1)
    assert p["asset_a"]["dollar_amount"] == 500 and p["asset_b"]["dollar_amount"] == 250


def test_forced_direction_strategies_ignore_zscore():
    a = C.calculate_position(1000, 0.5, 100, 50, S.LONG_ASSET_A, zscore=+3)
    assert (a["asset_a"]["side"], a["asset_b"]["side"]) == ("long", "short")
    b = C.calculate_position(1000, 0.5, 100, 50, S.LONG_ASSET_B, zscore=-3)
    assert (b["asset_a"]["side"], b["asset_b"]["side"]) == ("short", "long")
    assert b["asset_a"]["dollar_amount"] == 500 and b["asset_b"]["dollar_amount"] == 1000


@pytest.mark.parametrize("kw", [dict(capital=0), dict(capital=-5), dict(beta=0), dict(beta=-1),
                                dict(asset_a_price=0), dict(asset_b_price=-1)])
def test_calculator_rejects_invalid_inputs(kw):
    args = dict(capital=1000, beta=1, asset_a_price=1, asset_b_price=1)
    args.update(kw)
    with pytest.raises(ValueError):
        C.calculate_position(**args)


def test_estimated_pnl_golden():
    p = C.calculate_position(1000, 0.5, 100, 50, S.DOLLAR_NEUTRAL, zscore=-2)
    # long A $1000 +2% = +20 ; short B $500, B +1% = -5 ; total 15 = 1.5% of 1000
    r = C.calculate_estimated_pnl(p, 0.02, 0.01)
    assert r["pnl_a"] == pytest.approx(20) and r["pnl_b"] == pytest.approx(-5)
    assert r["total_pnl"] == pytest.approx(15) and r["return_pct"] == pytest.approx(1.5)


# ---- metrics --------------------------------------------------------------
def test_max_drawdown_golden():
    # peak 120 -> trough 90 = -25%
    assert M.calculate_max_drawdown(pd.Series([100, 120, 90, 110])) == pytest.approx(25.0)
    assert M.calculate_max_drawdown(pd.Series([100, 101, 102])) == 0.0
    assert M.calculate_max_drawdown(pd.Series([], dtype=float)) == 0.0


def test_total_return_golden_and_zero_initial():
    assert M.calculate_total_return(pd.Series([100, 150])) == pytest.approx(50.0)
    assert M.calculate_total_return(pd.Series([0, 5])) == 0.0
    assert M.calculate_total_return(pd.Series([], dtype=float)) == 0.0


def test_sharpe_golden_and_degenerate():
    r = pd.Series([0.01, -0.01, 0.02, 0.0])
    # mean 0.005, sample std = sqrt(((.005)^2+(.015)^2+(.015)^2+(.005)^2)/3) = 0.0129099
    assert M.calculate_sharpe_ratio(r) == pytest.approx(math.sqrt(365) * 0.005 / 0.0129099, rel=1e-4)
    assert M.calculate_sharpe_ratio(pd.Series([0.01, 0.01])) == 0.0  # zero std
    assert M.calculate_sharpe_ratio(pd.Series([], dtype=float)) == 0.0


def test_win_rate_and_profit_factor_golden():
    trades = [{"pnl": 10}, {"pnl": -5}, {"pnl": 20}, {"pnl": None}, {"pnl": -5}]
    assert M.calculate_win_rate(trades) == pytest.approx(50.0)  # 2 of 4 closed
    assert M.calculate_profit_factor(trades) == pytest.approx(3.0)  # 30 / 10
    assert M.calculate_win_rate([]) == 0.0 and M.calculate_profit_factor([]) == 0.0
    assert M.calculate_profit_factor([{"pnl": 5}]) == 999999.0  # no losses sentinel
    assert M.calculate_profit_factor([{"pnl": 0}]) == 0.0


def test_kelly_golden():
    # p=.6, b=2 -> (2*.6-.4)/2 = .4
    assert M.calculate_kelly_criterion(60, 20, 10) == pytest.approx(40.0)
    assert M.calculate_kelly_criterion(30, 10, 10) == 0.0  # negative edge clamps to 0
    assert M.calculate_kelly_criterion(0, 1, 1) == 0.0 and M.calculate_kelly_criterion(100, 1, 1) == 0.0
    assert M.calculate_kelly_criterion(60, 20, 0) == 0.0


def test_mae_metrics_golden():
    t = [{"max_adverse_excursion": -10, "mae_pct": -2.0}, {"max_adverse_excursion": -30, "mae_pct": -6.0}, {}]
    r = M.calculate_mae_metrics(t)
    assert r == {"avg_mae": -20.0, "max_mae": -30, "avg_mae_pct": -4.0, "max_mae_pct": -6.0}
    assert M.calculate_mae_metrics([])["avg_mae"] == 0.0


def test_leverage_floor_and_ratio():
    assert M.calculate_optimal_leverage(-1, 10)["recommended"] == 1.0
    r = M.calculate_optimal_leverage(2.0, 10.0)  # dd based = 1/.1*.5=5 ; sharpe 2 -> optimal 2 -> rec 2 (<=... )
    assert r["optimal_leverage"] == 2.0 and r["sharpe_based"] == 2.0 and r["drawdown_based"] == 5.0
    assert M.calculate_return_to_mae_ratio(10, -2) == 5.0
    assert M.calculate_return_to_mae_ratio(10, 0) == 999999.0


# ---- history analyzer --------------------------------------------------------
def test_metric_changes_new_removed_updated():
    cur = [{"asset_a": "A", "asset_b": "B", "correlation": 0.9, "beta": 1.1, "adf_pvalue": 0.01},
           {"asset_a": "C", "asset_b": "D", "correlation": 0.8, "beta": 2}]
    prev = [{"asset_a": "A", "asset_b": "B", "correlation": 0.7, "beta": 1.0, "adf_pvalue": 0.03},
            {"asset_a": "E", "asset_b": "F", "correlation": 0.5, "beta": 1}]
    out = {(c["asset_a"], c["asset_b"]): c for c in H.calculate_metric_changes(cur, prev)}
    assert out[("A", "B")]["status"] == "updated"
    assert out[("A", "B")]["correlation_change"] == pytest.approx(0.2)
    assert out[("A", "B")]["adf_pvalue_change"] == pytest.approx(-0.02)
    assert out[("C", "D")]["status"] == "new" and out[("E", "F")]["status"] == "removed"


def test_trends_and_degradation():
    assert H.analyze_trends([{"timestamp": "1", "results": []}])["total_pairs_trend"] == []
    hist = [{"timestamp": "2", "results": [{"correlation": 0.6}, {"correlation": 0.8}]},
            {"timestamp": "1", "results": [{"correlation": 0.5}]},
            {"timestamp": "0", "results": []}]
    t = H.analyze_trends(hist)
    assert [x["timestamp"] for x in t["total_pairs_trend"]] == ["1", "2"]  # sorted, empty skipped
    assert t["avg_correlation_trend"][1]["avg_correlation"] == pytest.approx(0.7)
    cur = [{"asset_a": "A", "asset_b": "B", "correlation": 0.6}, {"asset_a": "C", "asset_b": "D", "correlation": 0.79}]
    avg = {("A", "B"): {"avg_correlation": 0.8}, ("C", "D"): {"avg_correlation": 0.85}}
    d = H.detect_degradation(cur, avg)
    assert len(d) == 1 and d[0]["asset_a"] == "A" and d[0]["degradation"] == pytest.approx(0.2)

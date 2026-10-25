# Rule catalogue

Every formula below is taken from the code it names. File paths are relative to `backend/app/`. Defaults are the values in `modules/shared/models.py` (`ScreeningConfig`) and `config.py` unless stated otherwise. Units: prices in USDT, spreads in price units, `spread_std` in percent of the mean price of asset A, costs in basis points (bps), 1 bps = 0.01 %.

Notation: `a_t`, `b_t` are close prices of assets A and B on aligned bars `t = 1..n`.

## 1. Universe and pre-filters

| Rule | Where | Definition |
|---|---|---|
| Asset universe | `modules/screener/data_loader.py` `get_top_assets` | Binance USDT futures tickers (`BTCUSDT` style, dated delivery contracts skipped), volume = `quoteVolume` (fallback `volume`), kept if `volume_usd >= min_volume_usd` (default 1,000,000), sorted by volume, cut to `max_assets` (default 100, API range 10-500). Stablecoins are excluded. |
| History sufficiency | `modules/screener/screener.py` | `min_required_bars = int(bars_for_lookback(lookback_days, timeframe) * 0.8)`, where `bars_for_lookback = days * 1d_ms // candle_ms`. An asset with fewer bars is dropped before pairs are formed. |
| Correlation pre-filter | `_test_pair` | Pearson correlation of simple returns `r_t = a_t / a_{t-1} - 1` (and the same for B). Reject if `corr < max(0.7, 0.9 * min_correlation)` (fast rejection, before the cointegration test). |
| Final correlation | `_test_pair` | Reject if `corr < min_correlation` (default 0.80). |
| Minimum length | `cointegration.py` | Pair needs at least 50 aligned observations; otherwise it is rejected. |
| Half-life filter | `_half_life_ok` | Candidate is kept only if `min_half_life <= half_life <= max_half_life`. Defaults: min 1.0 bar, max unset. A pair with no half-life is rejected when either bound is set. |

## 2. Cointegration: Engle-Granger in both directions, Bonferroni x2

`cointegration.py` `CointegrationTester.engle_granger_test`.

1. OLS: `a_t = alpha + beta * b_t + e_t`. Hedge ratio `beta` and intercept `alpha` come from this regression.
2. Residuals: `e_t = a_t - (alpha + beta * b_t)`.
3. Spread std (percent of price A):
   `spread_std = std(e) / mean(a) * 100`.
4. Engle-Granger tests, statsmodels `coint(y, x, trend='c', autolag='AIC')`, run in both orientations:
   - `p_ab` from `coint(a, b)`,
   - `p_ba` from `coint(b, a)`.
   The decision uses the smaller p-value, `p_min = min(p_ab, p_ba)`. `coint` uses Engle-Granger / MacKinnon critical values, not plain ADF on estimated residuals.
5. Bonferroni for two looks: `p_adj = min(1, 2 * p_min)`.
6. Cointegrated if `p_adj < 0.10`. The value stored as `adf_pvalue` is `p_adj`.

On any exception the pair is returned as not cointegrated with `p = 1.0`.

## 3. Half-life of mean reversion (discrete OU)

`cointegration.py` `half_life(spread)`.

Fit by OLS the AR(1) form of the discrete Ornstein-Uhlenbeck process:

    Δs_t = θ * s_{t-1} + c + ε_t

    half_life = -ln(2) / θ          (in bars of the chosen timeframe)

Returns `None` when there are fewer than 20 spread points, fewer than 10 usable differences, `θ >= 0` (no mean reversion), or the result is not finite and positive.

## 4. Rolling z-score

`cointegration.py` `rolling_zscore(spread, window)`:

    w          = max(2, int(window))
    min_periods = max(2, w // 2)
    z_t        = (s_t - mean_w(s)_t) / std_w(s)_t        (trailing window, NaN -> 0)

In `_test_pair` the window is derived from the half-life when `half_life >= 1`:

    window = int(min(max(half_life, 5), max(5, n // 2)))

If there is no usable half-life, the static z-score `(s - mean(s)) / std(s)` over the full sample is used instead. The current z-score (`current_zscore`) is the last value of the chosen series.

## 5. Hurst exponent (generalized, Di Matteo)

`hurst.py` `generalized_hurst_exponent(series, max_lags=50, q=1)`.

    K_q(τ) = mean_t |X_{t+τ} - X_t|^q        for τ = 1 .. min(max_lags, n//2) - 1

Fit `log K_q(τ) = q * H * log τ + C` by least squares. Then `H = slope / q` (q = 1 here).

- Needs `n >= 2 * max_lags` observations and at least 5 usable τ values (K values <= 0 stop the loop).
- Interpretation: `H < 0.5` mean reverting, `H ~ 0.5` random walk, `H > 0.5` trending.
- Computed only when `include_hurst` is true. The live screener enables it; the `/screener/run` request defaults it to false.

## 6. Net edge after costs

`_test_pair`:

    gross_edge_pct = entry_z * spread_std
    fee_slip_pct   = 4 * (taker_fee_bps + slippage_bps) * 0.01
    holding_hours  = half_life * bar_hours             (bar_hours = timeframe length in hours)
    funding_pct    = (holding_hours / 8) * funding_bps_per_8h * 0.01     (0 if no half-life)

    expected_net_edge_pct = gross_edge_pct - fee_slip_pct - funding_pct

Defaults: `entry_z = 2.0`, `taker_fee_bps = 5`, `slippage_bps = 2` (so `fee_slip_pct = 2.8`), `funding_bps_per_8h = 1`. The four fills are two legs, open and close. The `/screener/run` API does not expose the cost fields, so the defaults apply there.

## 7. Composite score

`_test_pair`, output `composite_score` in the range 0-100:

    correlation_score = corr                                       (0..1)
    adf_score         = clamp(1 - adf_pvalue / 0.1, 0, 1)          (0.1 is hard-coded)
    hurst_score       = clamp((0.5 - H) / 0.5, 0, 1)   if H computed, else 0
    net_edge_score    = clamp(net_edge_pct / gross_edge_pct, 0, 1) if gross > 0, else 0

    composite_score = 100 * (0.40 * correlation_score
                           + 0.25 * adf_score
                           + 0.15 * hurst_score
                           + 0.20 * net_edge_score)

Without Hurst the maximum is 85. The results are sorted by `corr * (1 - adf_pvalue)` (descending) before the API returns them. The live monitor ranks pairs by `composite_score`.

## 8. Multiple testing: Benjamini-Hochberg FDR (opt-in)

`screener.py` `screen_pairs`.

1. Candidates are pairs that pass the correlation and half-life filters.
2. BH is always computed for the q-values, with `alpha = max_adf_pvalue` (default 0.10), using statsmodels `multipletests(method='fdr_bh')`. Each candidate gets `adf_pvalue_fdr` (the BH-adjusted p).
3. If `use_fdr` is true, the kept set is the BH rejections. The default is `use_fdr = false`, which is not settable through the HTTP API, only in code.
4. Otherwise the filter is the raw threshold `adf_pvalue <= max_adf_pvalue`.

Note: `_test_pair` drops non-cointegrated pairs early only when `use_fdr` is false. With FDR on, all correlation-passing pairs reach the BH step.

## 9. Clustering (opt-in)

`screener.py` `_clustered_pairs`, enabled by `use_clustering` (default false):

1. Returns `r_t = p_t / p_{t-1} - 1` on the aligned matrix (rows with NaN dropped).
2. Distance `d_ij = 1 - corr(r_i, r_j)`, symmetrized, clipped to [0, 2].
3. Average-linkage hierarchical clustering (`scipy.cluster.hierarchy.linkage`), cut with `fcluster(criterion='distance', t = cluster_distance)`, default `cluster_distance = 0.5`.
4. Only pairs inside the same cluster are tested. If there are fewer than 10 aligned rows or 2 series, all pairs are used.

## 10. Alerts

`modules/alerts/alert_manager.py` `Alert.check`. For a z-score `z`:

    triggered = (threshold_high is set and z >= threshold_high)
             or (threshold_low  is set and z <= threshold_low)

If an alert is created without thresholds, `threshold_high = 2.0` and `threshold_low = -2.0`. Each trigger increments `trigger_count` and sets `last_triggered` (UTC). Alerts are stored and checked inside the application only; there is no external notification channel.

## 11. Intraday live hedge: Kalman filter

`screener/kalman.py` `KalmanHedge` and `intraday_monitor.py`.

State `x_t = [beta_t, alpha_t]` follows a random walk; observation `a_t = [b_t, 1] x_t + v_t`.

    Q = delta / (1 - delta) * I        (delta = INTRADAY_KALMAN_DELTA, default 1e-4)
    R = r                              (INTRADAY_KALMAN_R, default 1e-3)
    x_0 = [a_0 / b_0, 0],  P_0 = I

For each step `t`:

    P   = P + Q                        (t > 0)
    e_t = a_t - H x                    H = [b_t, 1]
    S_t = H P H' + R
    K   = P H' / S_t
    x   = x + K e_t
    P   = P - K H P
    zscore_t = e_t / sqrt(S_t)         (the innovation z-score, self-normalizing)

The live monitor:

- Fetches recent candles on `INTRADAY_KALMAN_TIMEFRAME` (default `5m`) over `INTRADAY_KALMAN_LOOKBACK_DAYS` (default 3) for both legs, bypassing the screener cache.
- Requires at least `MIN_KALMAN_BARS = 60` aligned candles, otherwise the pair is counted in `skipped_pairs`.
- Takes the last value of `beta`, `spread` (innovation) and `zscore`.
- Flags `is_unusual = |zscore| >= INTRADAY_ZSCORE_ALERT_THRESHOLD` (default 2.5).
- Tracks the top `INTRADAY_TOP_PAIRS` (default 20) daily pairs by `composite_score`.
- Compares with the daily z-score: `zscore_delta = zscore - daily_zscore`.

## 12. Backtester

`modules/backtester/strategy.py` and `backtester.py`.

- Entry: `z <= -entry_threshold` opens a long spread (long A, short B); `z >= entry_threshold` opens a short spread. Default `entry_threshold = 2.0`, API range 0.5-5.
- Exit: stop-loss at `|z| >= stop_loss` (z-score type). Take-profit is defined in z-score terms: a non-negative value targets the opposite side after crossing zero, a negative value targets the same side before zero. Percent and ATR variants are selected by `*_type` (`percent` default).
- Hedge ratio: rolling 90-bar OLS beta and alpha, excluding the current bar (no look-ahead). A fixed `beta` can be passed instead.
- Costs: `transaction_cost_pct` (default 0.1 %) of notional on every trade, entry, exit and rebalance.
- Optional rebalancing when beta drifts by `rebalancing_threshold` (default 5 %), at most every `rebalancing_frequency_days` (default 5).

## 13. Backtest metrics

`modules/backtester/metrics.py`:

    Sharpe        = sqrt(365) * mean(r - rf) / std(r)        rf = 0; 365 for 24/7 crypto
    Max drawdown  = |min_t((E_t - max_{s<=t} E_s) / max_{s<=t} E_s)| * 100     (percent, positive)
    Win rate      = winning trades / all trades
    Profit factor = gross profit / gross loss
    Kelly         = (b*p - q) / b,  b = avg_win / avg_loss,  p = win_rate / 100,  q = 1 - p
                    (returns 0 when avg_loss <= 0 or win rate is 0 or 100 %)
    Return/MAE    = total return divided by the MAE measure (alternative risk measure to Sharpe)

Also reported: total return, optimal leverage from Sharpe and drawdown, MAE metrics.

## 14. Position sizing and PnL

`modules/calculator/position_calculator.py`. Direction from the z-score sign: `z > 0` means short A and long B; otherwise long A and short B.

| Strategy | Dollar A | Dollar B |
|---|---|---|
| `dollar_neutral` (default) | `capital` | `capital * beta` |
| `equal_dollar` | `capital / 2` | `capital / 2 * beta` |

| `long_asset_a` | `capital` (always long A) | `capital * beta` (always short B) |
| `long_asset_b` | `capital * beta` (always short A) | `capital` (always long B) |

The `long_asset_*` strategies ignore the z-score direction.

Inputs must be positive (`capital`, `beta`, both prices), else `ValueError`.

PnL (`modules/positions/position_manager.py` `calculate_pnl`):

    long position:   pnl_a = (price_a - entry_a) * qty_a,   pnl_b = (entry_b - price_b) * qty_b
    short position:  pnl_a = (entry_a - price_a) * qty_a,   pnl_b = (price_b - entry_b) * qty_b
    total = pnl_a + pnl_b

Positions are bookkeeping records only. Nothing is sent to an exchange.

## 15. Data-layer indicators

`backend/app/data_layer/processing/indicators.py` `compute_indicators` computes, per symbol and timeframe, the values served by `GET /indicators` of the market data layer:

- EMA over periods 9, 21, 50, 200.
- RSI, period 14.
- Bollinger bands, period 20, 2 standard deviations.
- ATR, period 14.
- VWAP.
- Volume SMA, period 20.

The data layer is a separate service (see README, "Market data layer").

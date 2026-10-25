# Progress Log

Running log of what's been done, why, and what's still pending. Newest entries on top.

---

## 2026-06-16

### Done — cointegration methodology fixes (round 1)
Research-driven correctness pass on the screener's statistics. Sources: statsmodels
`coint` vs `adfuller` distinction, Engle-Granger/MacKinnon critical values, Hudson &
Thames on multiple-testing/FDR, OU half-life.

- **`cointegration.py`**:
  - Replaced manual `adfuller(residuals)` with `statsmodels.tsa.stattools.coint`.
    The old code ran a plain ADF on *estimated* OLS residuals and used standard
    Dickey-Fuller p-values — those crit. values are too lenient for residuals and
    overstate cointegration (false pairs). `coint` applies the proper
    Engle-Granger / MacKinnon-Phillips-Ouliaris critical values. OLS is still run
    separately to recover beta/alpha/spread_std. Return tuple unchanged
    (`adf_statistic`/`adf_pvalue` now carry the EG stat/pvalue).
  - Added `half_life(spread)` — OU/AR(1) `Δs = θ·s_{t-1}+c`, `HL = -ln2/θ` in bars.
    Returns None if not mean-reverting (θ≥0).
  - Added `rolling_zscore(spread, window)` — trailing-window z to avoid the
    full-sample lookahead of the static z-score.
- **`screener.py`**:
  - `_test_pair` now computes `half_life`; `current_zscore` uses the rolling
    z-score with window = half-life (falls back to static z when no half-life).
  - Half-life filter (`config.min_half_life` default 1.0, `max_half_life` None).
  - **FDR (Benjamini-Hochberg)** across candidate p-values (`config.use_fdr`,
    default True, alpha=`max_adf_pvalue`). N*(N-1)/2 pairs at raw p<0.10 yields
    hundreds of spurious pairs; BH controls the false-discovery fraction.
- **Plumbing**: `half_life` added to `ScreeningConfig` (+`min/max_half_life`,
  `use_fdr`), `PairsScreeningResult` (DB col) + lightweight additive migration
  `_ensure_columns()` in `database.py` (create_all never ALTERs existing tables),
  `PairResult` schema, all 3 `PairResult` constructions in `routes.py`, CSV export
  columns, frontend `api.ts` types, new **HL column** in `PairsTable.tsx`.
- Smoke-tested on synthetic OU-cointegrated series: beta 1.47 (true 1.5),
  half-life 6.7 bars (true 6.93), `coint` p≈0; methods verified.

Note: project `.venv` in this checkout was empty — installed numpy/pandas/
statsmodels/scipy to run the verification.

### Done — Kalman dynamic hedge ratio for live monitor (round 2, item 1)
- **New `kalman.py`** (`KalmanHedge`): online time-varying hedge ratio. State
  `[beta, alpha]` random walk, observation `a_t = beta·b_t + alpha`. The Kalman
  innovation is the spread; `innovation / sqrt(innovation_var)` is a
  self-normalizing z-score (no separate rolling mean/std). Tunable via `delta`
  (beta agility) and `r` (obs noise).
- **`intraday_monitor.py` rewired**: `_update` now re-fits beta/alpha on recent
  intraday candles (`INTRADAY_KALMAN_TIMEFRAME` default 5m, `_LOOKBACK_DAYS` 3)
  per top pair via the Kalman filter, instead of applying the stale daily fit to
  a single live ticker. Removed the `MAX_ZSCORE_DELTA` hack and the now-dead
  `_fetch_prices*` / httpx code — the hack only existed to hide stale-beta blowups,
  which dynamic beta fixes at the source. Last candle close ≈ live price.
- **Config**: `INTRADAY_KALMAN_TIMEFRAME/_LOOKBACK_DAYS/_DELTA/_R`.
- Smoke-tested: filter tracked a beta drifting 1.2→1.8 (recovered 1.26→1.82),
  z-scores finite, empty-input guard OK. Snapshot dict shape unchanged, so
  `LiveMonitor.tsx` needs no change.
- Cost: fetches intraday candles for top_n pairs per refresh (cached in
  DataLoader). Heavier than the old single ticker batch; relies on cache.

### Done — Engle-Granger both-direction test (round 2, item 2)
- **`cointegration.py`**: `engle_granger_test` now runs `coint(a,b)` and
  `coint(b,a)` and uses the lower p-value as the cointegration decision. EG is
  direction-sensitive (residual normalized differently each way), so the
  arbitrary a~b orientation could reject a genuinely cointegrated pair. The
  hedge ratio (beta/alpha) stays canonical a~b for the downstream spread.
- Smoke-tested: picks min(p_ab, p_ba); beta recovered 1.285 (true 1.3).
- Cost: doubles the `coint` calls per pair (the expensive step). Acceptable;
  revisit if full-universe fine-TF scans get slow.

### Done — cost-aware scoring (round 2, item 3)
- **Cost model** (`config.py`): `TRADING_TAKER_FEE_BPS` (5), `_SLIPPAGE_BPS` (2),
  `_FUNDING_BPS_PER_8H` (1), `_ENTRY_ZSCORE` (2.0) — Binance-USDT-M-ish defaults,
  all overridable.
- **`screener.py` `_test_pair`**: computes `expected_net_edge_pct` =
  `entry_z·spread_std%` (gross reversion from |z|=entry to 0) minus
  `4·(fee+slippage)` (round-trip, 2 legs open+close) minus funding over the
  holding period (`half_life · bar_hours / 8 · funding_bps`). `bar_hours` from
  `TIMEFRAME_MS`.
- **composite_score reweighted** to fold in a net-edge term:
  `corr·0.4 + adf·0.25 + hurst·0.15 + net_edge·0.2`, where `net_edge` =
  `clamp(net/gross, 0, 1)`. A statistically perfect pair whose amplitude can't
  clear costs now loses that 0.2 (caps ~80 instead of 100).
- **Plumbed** `expected_net_edge_pct` through DB col (+migration), schema,
  routes (3×), CSV, `api.ts`, and a new **Net%** column (green>0/red≤0) in
  `PairsTable.tsx`.
- Integration smoke (monkeypatched data fetch): tiny-amplitude reverter →
  gross 0.059% < 0.28% cost → net −0.225% → net_edge_score 0 → composite 80
  (vs 100). Mechanism verified. (Note: existing DB rows keep their old-weight
  scores until re-screened.)

### Done — universe pre-clustering (round 2, item 4)
- **`screener.py` `_clustered_pairs`**: when `config.use_clustering` is on,
  builds a return-correlation matrix over the valid assets, average-linkage
  hierarchical clustering on `1 - corr` distance, cut at `config.cluster_distance`
  (default 0.5). Only within-cluster pairs are tested. Falls back to all-pairs on
  any failure. Cuts tests + false discoveries, focuses on related assets.
- Config: `use_clustering` (default False), `cluster_distance` (0.5). Echoed in
  stats. `api.ts` types updated.
- Smoke: 5 assets in 2 factor-driven groups -> {A,B,C}+{D,E} -> 4 within-cluster
  pairs vs 10 all-pairs; cross-cluster pairs removed.

### Done — surface controls + cost params per-run (round 2, item 5)
- **Cost params moved into `ScreeningConfig`** (`taker_fee_bps`, `slippage_bps`,
  `funding_bps_per_8h`, `entry_zscore`) so they're tunable per run; `_test_pair`
  reads them from config. Removed the now-dead `TRADING_*` block from
  `config.py` and the unused `settings` import in `screener.py`.
- **`ScreenerSettings.tsx`**: new "Methodology & costs" section — min/max
  half-life, FDR toggle, clustering toggle + distance slider, and the 4 cost
  inputs (entry z, fee, slippage, funding) with a net-edge formula note.

### Pending — methodology round 2 (remaining)
- (none — items 1-5 done. Future: walk-forward / out-of-sample beta stability,
  Johansen for >2-asset baskets, live cost feed for funding instead of a constant.)

### Done — Docker deploy + verify
- `docker compose build backend datalayer` + `up -d` (full stack: redis,
  postgres, datalayer, backend, frontend). No Dockerfile/requirements change
  needed — FDR uses `statsmodels.stats.multitest`, Kalman is pure numpy,
  clustering uses scipy (already pinned).
- Verified live: backend `/health` → healthy (45 pairs); startup clean (no
  tracebacks); additive migration ran — `PRAGMA table_info` in the container DB
  confirms `half_life` and `expected_net_edge_pct` columns both present.
- Stack: http://localhost:3100 (frontend), :8000 (backend), :8001 (datalayer).

### Env note
- This checkout's `.venv` was empty; over this session installed the declared
  deps to run verification: numpy, pandas, statsmodels, scipy, ccxt, sqlalchemy,
  pydantic, pydantic-settings. (Full set still in `backend/requirements.txt`.)

---

## 2026-06-15

### Done
- **Fixed `/run` background-screening status reporting** (`backend/app/api/routes.py`, `backend/app/api/schemas.py`).
  - `/status` previously only reflected the live-screener's internal `is_running`
    flag, not the separate `_screening_in_progress` flag used by the Settings
    "Run Screening" button (`POST /run`). The frontend never saw that a scan
    was running, so it didn't poll for fresh results.
  - `/status` now returns `is_running = live_screener.is_running or _screening_in_progress`
    plus a new `last_error` field.
  - If `_run_screening_background` raises, the error is now stored in
    `_last_run_error` instead of being silently swallowed (old results stayed
    on screen with no indication anything failed).
- **`ScreenerSettings.tsx`**: after clicking "Run Screening", the modal now
  polls `/status` (up to 5 min) and shows an `alert()` if `last_error` is set.
- **Added `max_assets` slider to Settings**, with per-timeframe defaults/limits
  (1m: 15/30, 5m: 30/50, 15m: 50/100, 1h/4h/1d: 100/200). Fine timeframes need
  many more paginated OHLCV requests per asset (Binance caps at 1000
  candles/request), so scanning the full 100-asset universe at 1m was likely
  timing out or rate-limiting and silently leaving old results in place.
- Frontend `api.ts`: added `max_assets` to `ScreeningConfig`, `last_error` to
  `ScreeningStatus`.

Commit: `75f8060`.

### Earlier this session
- Fixed `RuntimeError: generator didn't stop after throw()` in `get_db()`
  (`backend/app/database.py`) - removed post-`yield` exception handlers that
  re-yielded; replaced with a `finally`-based close. Commit `5aa3b30`.
- Fixed `/run-live` returning 500 instead of 400 when a screening run was
  already in progress (missing `except HTTPException: raise`). Part of
  commit `5aa3b30`.
- Added intraday **timeframe selector** (1m/5m/15m/1h/4h/1d) to
  `ScreenerSettings.tsx`, with per-timeframe lookback-day ranges so short
  candles still span enough independent cycles to be statistically meaningful
  (no "1-day lookback on 1m candles" overfitting). Plumbed `timeframe` through
  `ScreeningConfig` → `DataLoader.fetch_ohlcv`/`get_price_series`
  (`TIMEFRAME_MS`, `bars_for_lookback`) → `PairsScreener` → results/DB →
  `PairResult.timeframe` → "TF" column in `PairsTable.tsx`. Commit `6ac7b2d`.
- Fixed intraday live monitor showing nonsensical z-scores (e.g. BTC/XRP
  -682.71) for pairs whose daily-fitted hedge ratio no longer matches live
  prices: added `MAX_ZSCORE_DELTA = 5.0` in `intraday_monitor.py` - pairs where
  `|live_z - daily_z| > 5` are dropped instead of shown. Commit `bfaaf7c`.

### Pending / not started
- **Live Monitor expanded-row detail view**: currently just a tiny sparkline
  + "Collecting live data...". User wants it as rich as the Screener's "Spread
  Analysis" pair-detail modal (`PairDetails.tsx` stats: mean reversion,
  current deviation, expected return, risk metrics, return probabilities).
- **Continuous data ingestion**: rework `DataLoader` to read from
  `backend/app/data_layer`'s stored candles instead of per-request ccxt REST
  calls. This is the real fix for making 1m/5m screening fast/feasible at
  scale (avoids per-asset pagination through Binance's 1000-candle limit on
  every screening run).
- Verify end-to-end: run a 1m screening via Settings with the new
  `max_assets` cap and confirm results actually come back with `TF: 1m` and
  different beta/correlation values than the daily scan.
- Two separate "Run screening" triggers still exist in the UI:
  - top-right header button → `runLiveScreening()` → `/run-live` (uses
    server-side default `ScreeningConfig` from `app.config.settings`, ignores
    Settings-modal timeframe/max_assets).
  - Settings modal → `runScreening(settings)` → `/run` (uses the configured
    timeframe/max_assets).
  Consider clarifying in the UI which button does what, or unifying them.

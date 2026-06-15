# Progress Log

Running log of what's been done, why, and what's still pending. Newest entries on top.

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

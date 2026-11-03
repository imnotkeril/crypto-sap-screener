# QA report - Statistical Arbitrage Pairs Screener (2026-10-25, branch chore/audit)

Verdict: **RED (conditional)** - 0 failing tests, but open bugs (5 pinned as strict xfail; others documented below). (updated 2026-11-03: BUG-1 fixed; 112 passed, 4 xfailed: BUG-3, 5, 6, 7). Not GREEN until BUG-3, BUG-6 are fixed or consciously accepted.

## Risk map
| Area | Tier | Tests | Result |
|---|---|---|---|
| Position calculator (sizing, side, P&L) | A (money) | test_calculator_metrics.py (hand-computed goldens, invalid inputs) | PASS |
| Position manager + /positions API (CRUD, PnL, validation) | A | test_alerts_positions.py | PASS |
| Backtester accounting (pnl legs, equity reconciliation, costs) | A/B | test_backtester.py | PASS (BUG-8 pinned) |
| Backtest metrics (Sharpe, DD, win rate, PF, Kelly, MAE, leverage) | B | test_calculator_metrics.py | PASS |
| Alerts (manager + API CRUD, dedupe/cooldown) | B | test_alerts_positions.py | PASS + 1 xfail (BUG-3) |
| Auth matrix (none / bad / empty / good key / cron secret) | A | test_alerts_positions.py, test_api_security.py | PASS |
| Exports csv/excel (golden, filters, empty) | B | test_alerts_positions.py | PASS |
| Live-screener overlap / failure / degraded-empty run | B | test_alerts_positions.py | PASS + 2 xfail (BUG-5, BUG-6) |
| Stale / empty / failing feed (intraday monitor) | B | test_stale_feed.py | PASS + 1 xfail (BUG-7) |
| History analyzer | B | test_calculator_metrics.py | PASS |
| Cointegration/Hurst/Kalman/net-edge | B | pre-existing test_stats.py, test_screener.py | PASS |
| Frontend UI | C | not tested | browser pass not done |

## Commands and counts
Python: venv2 (scratchpad), `PYTHONIOENCODING=utf-8`, tests run on a temp sqlite DB (`statarb-tests-*/test.db`, set in `backend/tests/conftest.py`), no network.

```
BEFORE (cd backend && python -m pytest -q):  23 passed, 5 warnings in 16.68s
AFTER  (cd backend && python -m pytest -q):  88 passed, 5 xfailed in 11.66s   (0 failed, 0 skipped)
```
New: 65 tests in 4 files (+5 strict xfail = open bugs). `tsc --noEmit`, `mypy app`, `npm run build` (Vite) were NOT re-run in this pass (frontend/typing outside the scope given).

## Live check (one scan, temp sqlite, port 28481, API_KEY=x, AUTO_SCREEN_ON_COLD_START=false)
- GET /health 200; GET status/results/stats/trends/export/csv 200 with key; no key 401.
- POST /api/v1/screener/run `{"assets":[BTC,ETH,SOL,BNB,XRP,DOGE],"lookback_days":60,"max_assets":10}`: accepted instantly, finished by the second 5 s poll: **scan duration 5-12 s** (poll granularity 5 s; session reports 15 pairs tested, 2 found: XRP/DOGE, ETH/XRP). Server log: 0 errors/warnings/tracebacks. Server stopped afterwards (port closed).
- Freshness SLA (ASSUMED, none defined in the repo): live screener interval is 1800 s (`live_screener.py` screening_interval), so assume "results no older than 30 min". A 6-asset scan at 12 s is far inside it, but this is NOT a full-universe load test: the default universe (SCREENER_MAX_ASSETS) was not scanned, so SLA compliance for the full universe is unproven. Linear extrapolation is not valid (pairs grow O(n^2), exchange rate limits).

## Findings (hand-computed goldens)
- Calculator: capital 1000, beta 0.5, 100/50, z=-2 -> long A 10 units $1000, short B 10 units $500, net exposure 500; est. P&L +2%/+1% -> +20 / -5 = 15 (1.5%). Matches code.
- Metrics: DD [100,120,90,110] = 25%; profit factor 30/10 = 3; win rate 2/4; Kelly(60%, b=2) = 40%; Sharpe sqrt(365)*0.005/0.0129099. Matches.
- Backtester (synthetic, tc=0): trade pnl == pnl_a + pnl_b == leg math from entry/exit prices; final equity == 10000 + sum(closed pnl). Matches.

## Bugs
| ID | Sev | Where | Description | Test |
|---|---|---|---|---|
| BUG-1 | high | `backend/app/api/routes_alerts.py` check_triggered_alerts (~L215-245) vs CRUD (L33-150) | CRUD persists alerts to DB, but `/alerts/triggered/check` and `live_screener._run_screening` evaluate only the in-memory `AlertManager`. Alerts created through the API never fire. | **FIXED** 6b47b26: `/alerts/triggered/check` evaluates DB alerts matched by (asset_a, asset_b); test_db_alert_fires_in_triggered_check now a normal test |
| BUG-3 | med | `backend/app/modules/alerts/alert_manager.py` Alert.check (L52-68) | No dedupe/cooldown: every check above threshold re-triggers and increments trigger_count (spam if notifications are added). Feature is absent, not partially working. | xfail test_alert_cooldown_dedupes_repeated_checks + current-behaviour test |
| BUG-4 | low | `routes_alerts.py` create_alert (L58-90) | Identical alert definitions for the same pair accepted repeatedly. | test_alert_api_duplicate_create_is_not_deduped (documents) |
| BUG-5 | med (latent) | `backend/app/modules/screener/live_screener.py` start() L116-125 vs _run_screening L176-181 | `start()` sets `is_running=True`, the loop thread then calls `_run_screening`, whose guard sees running and skips forever. start() is currently never called (dead path), so only latent. | xfail test_live_screener_start_loop_actually_runs |
| BUG-6 | med | `backend/app/api/routes.py` run_screening L206-250, _run_screening_background L251 | POST /screener/run checks only `_screening_in_progress` (set later inside the background task) and ignores `live_screener.is_running`; two quick requests, or run + run-live/cron, can scan concurrently and overwrite `current_results`. Also `cron/run` returns "completed" even when its run was skipped due to overlap (routes.py L163-176). | xfail test_run_endpoint_rejects_overlap_with_live_scan |
| BUG-7 | med | `backend/app/modules/screener/intraday_monitor.py` _update (~L150-200) | Candle timestamps are never checked: a feed whose last candle is days/months old produces a snapshot stamped `updated_at=now` and live z-score signals. No stale-feed detection. | xfail test_stale_candles_are_rejected |
| BUG-8 | low | `backend/app/modules/backtester/backtester.py` L624, L785 | Exit cost is charged on the entry notional (`dollar_a+dollar_b`) instead of the exit-price notional. | test_costs_reduce_final_equity_by_expected_amount (pinned) |
| OBS | info | `strategy.py` generate_signals L88-118 | With open position and take_profit_type 'zscore' and target not reached the signal stays None (not HOLD); harmless if the backtester does not consume it. | - |

Fixed by QA: none (product code out of scope). Xfail markers are strict, so fixing a bug will fail the test until the marker is removed.

## Scheduler/auth results
- Overlap: second `_run_screening` while one runs is skipped, `run_manual` raises ValueError, flag reset after success and after exception, degraded empty result keeps previous good results (PASS).
- Not tested: process kill mid-scan / restart (state is in-memory + best-effort DB restore at construction), cron schedule definition (no scheduler config in repo to verify UTC), 1000-job load.
- Auth: protected routes 401 for no key / wrong key / empty key / cron secret; cron endpoint accepts Bearer CRON_SECRET or API key, rejects missing Bearer prefix and wrong values; 6/min limiter on expensive endpoints returns 429 on the 3rd call when limit=2 (PASS).

## Not covered / residual risk
- Browser pass not done (playwright MCP not installed, no built-in browser tools): table UI, 375/768/1440 layouts, console errors, a11y untested.
- Full-universe scan time vs SLA; only a 6-asset scan measured (once).
- Live exchange behaviour (rate limits, ticker failures in /calculate-position, which fetches live prices; not unit-tested because it needs the network or deeper mocking).
- Notifications/delivery channels: none exist in the code (alerts only compute triggers); nothing to test.
- /screener/pairs/{id}/export, spread endpoints, Redis path, data_layer package, FDR option via API: not covered.
- tsc/mypy/frontend build not re-run.
- Multi-process deployments: in-memory rate limiter, alert manager and `_screening_in_progress` are per-process.

Read: E:/Main/coding-brain paths per step brief: process/qa.md (opened), step-brief output (routers/finance/screener items listed, not opened individually)

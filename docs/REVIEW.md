# Review - audit fixes - HEAD~12 (4ef0be3)..b9804c2 + working tree - 2026-10-25

## Summary
| Reviewer | P0 | P1 | P2 | Status |
|---|---|---|---|---|
| reviewer (correctness/quality, opus) | 0 | 10 | 10 | done (this file) |
| security-reviewer | 0 | 2 | 5 (+3 P3) | done separately: `docs/SECURITY.md` (not duplicated here) |
| design-reviewer | - | - | - | **NOT DONE** (out of scope of this pass; no screenshots 375/768/1440, design gate open) |

Scope: `git diff HEAD~12` (auth/CORS/cron/rate limit, Hurst fix, FDR/Bonferroni, net-edge, Kalman live monitor, Docker) plus the code paths those changes feed (data loader, alerts, backtester, spread chart). Untracked QA tests (`backend/tests/test_alerts_positions.py`, `test_backtester.py`, `test_calculator_metrics.py`, `test_stale_feed.py`) were included in the test run. No `docs/SPEC.md` exists, so "AC" = the claims in `docs/plan.md` T2-T11 and the router finance checklist rows.
Already reported by QA (`docs/QA.md`) and not repeated: BUG-1 (DB alerts never fire), BUG-3 (no alert dedupe/cooldown), BUG-5 (`LiveScreener.start` loop never screens), BUG-6 (overlapping scans), BUG-7 (stale-candle detection), BUG-8 (exit cost on entry notional). Already reported by security: S-04 (cron `async def` blocks event loop) and S-03 (limiter keyed on proxy IP).

Exit check: P0 = 0, **P1 = 10 open** -> review does NOT pass. Design gate not run -> "zero ban fails" unverified.

## Findings
| id | sev | where | problem / fix | status |
|---|---|---|---|---|
| R-01 | P1 | backend/app/modules/screener/data_loader.py:233-242,325-327; screener.py:437-443 | Lookahead/flicker via the still-forming bar: `since = now - num_candles*candle_ms` with `limit=num_candles+5` returns the current open candle and `df.tail(num_candles)` keeps it, so `current_zscore` (and alerts via alert_manager.py:242-247) is computed on an unfinished close. Router build/review rule: forming bar excluded. Fix: drop rows with `timestamp + candle_ms > now` in `fetch_ohlcv`; test with a fake clock. | open |
| R-02 | P1 | backend/app/modules/screener/cointegration.py:234-239; screener.py:437-440 | Rolling z-score window = half-life clamped to >= 5 bars. With sample std over w points the last point's |z| is bounded by (w-1)/sqrt(w): w=5 -> 1.789, w=6 -> 2.041, w=8 -> 2.475 (verified: a 1e5-sigma shock gives exactly these values). For every pair with half-life < 6 bars `current_zscore` can never reach the entry z 2.0 / default alert thresholds +-2 (alert_manager.py:106-108); z is compressed for any half-life < ~10. Fix: window = k*half-life with a floor of >= 20-30 bars (or EWMA with span ~ half-life), and a test asserting a planted shock reaches |z| > 3. | open |
| R-03 | P1 | backend/app/modules/screener/kalman.py:289,316-317,333; config.py:52-53 | Kalman z is not scale-invariant: `R=1e-3` and `Q=delta/(1-delta)*I` are absolute, in price units. Evidence (same synthetic pair): prices x1e-4 -> std(z)=0.001; x1 and x1000 -> std(z)=0.49 (not 1, so the 2.5 threshold is ~5 sigma). A=1000*B pair with a planted 10-sigma last-bar shock: z_last=69 with std(z)=8.9 (constant false alerts); same pair with A rescaled /1000: z_last=0.07. Low-priced coins (DOGE/SHIB/PEPE) never flag, high-priced pairs always flag. Fix: run the filter on log prices or prices normalised by their first value, estimate R from the OLS residual variance of the warm-up window, scale Q per state; test z dispersion ~1 across price scales. | open |
| R-04 | P1 | backend/app/api/routes.py:219-228; schemas.py:11-20; frontend/src/components/ScreenerSettings.tsx:44-49,332-411 | UI sends `use_fdr`, `min/max_half_life`, `use_clustering`, `cluster_distance`, `taker_fee_bps`, `slippage_bps`, `funding_bps_per_8h`, `entry_zscore`, but `ScreeningConfigRequest` has none of these fields (pydantic drops extras) and `/run` builds `ScreeningConfig` without them. The FDR toggle, half-life filter, clustering and cost model in the settings panel are silently ignored; T7/T9 features are unreachable from the UI. Fix: add the fields with bounds to the request schema and pass them through; API test that `use_fdr=true` reaches `screen_pairs`. | open |
| R-05 | P1 | backend/app/modules/alerts/alert_manager.py:231-248; screener/screener.py:214-215 | Pair id = rank index (`idx + 1`) reassigned on every scan; alerts are matched by `pair_id` only, never by `asset_a/asset_b`. After the next scan alert for pair 3 is evaluated on whatever pair ranks 3rd. (Masked today for DB users by QA BUG-1; hits in-memory mode and resurfaces once BUG-1 is fixed.) Fix: key results and alerts by the canonical `(asset_a, asset_b)` pair, not by rank. | open |
| R-06 | P1 | backend/app/api/routes.py:120-123; live_screener.py:308; frontend/src/components/ScreenerDashboard.tsx:55 | Cold-start auto-scan (new `AUTO_SCREEN_ON_COLD_START=True`) fires whenever `last_session is None`. A failing scan (Binance 451/418, `get_top_assets` raises) leaves `last_session_info` unset, so every `/status` poll (every 10 s) starts a new full scan with `fetch_tickers` -> retry storm against an exchange that escalates 418 bans. Fix: record a failed session/backoff timestamp and do not auto-start more than once per N minutes; never auto-start after a 418/429. | open |
| R-07 | P1 | backend/app/modules/backtester/backtester.py:149-153,171-172; api/routes.py:596-597,620-629 | Lookahead in the backtester: rolling beta outside (0, 10] falls back to the FULL-SAMPLE beta/alpha (lines 72-87, fit on all data incl. the future). Beta is a price-unit ratio (documented as correct, test_stats.py:51-57, STATE "70/544"), so for pairs like SOL/DOGE every bar uses the future-fitted hedge. The spread chart has the same cap and then falls back to a static full-sample z. Fix: remove the `> 10` cap (validate sign/finite only) or fit on log prices; never fall back to the full-sample fit inside the loop (skip the bar instead). | open |
| R-08 | P1 | backend/app/modules/backtester/backtester.py:325-326,432-433,676-679 | Z-score stop-loss is inverted: UI says "Exit at Xσ against" (BacktestSection.tsx:211), but LONG (entered at z <= -entry) stops at `z >= +stop` (favourable side) and SHORT at `z <= -stop`. Adverse moves are never stopped; profitable overshoots are labelled `stop_loss`. Fix: LONG stop when `z <= -stop`, SHORT when `z >= +stop`; golden test per side. | open |
| R-09 | P1 | backend/app/modules/backtester/backtester.py:197-227,500-513,566 | Signal from the close of bar i is filled at the same close i (`entry_price_a = price_a_val`); exits likewise. Finance checklist rows 1/3: decide-and-fill on the same close. Fix: queue the signal and fill at bar i+1 (open if available, else next close) plus slippage. | open |
| R-10 | P1 | backend/app/modules/screener/data_loader.py:399-455,512-528 | Price cache has no TTL: memory and pickle file are keyed `symbol_days` / `symbol_tf_days` without time and reused while `len >= 80%` of expected bars. The 30-min live screener and `/run` keep re-screening the first downloaded history (file cache survives restarts); `current_zscore`, half-life and alerts stop moving. Only `/pairs/{id}/spread` clears it, and only on short data (routes.py:558-564). Fix: store last bar time with the cache and refetch (incrementally) when the last closed bar is older than one candle; show "data as of" in the UI. | open |
| R-11 | P2 | backend/app/modules/screener/screener.py:168-205,397-410; schemas.py:31-52 | BH m is shrunk: candidates are only correlation- and half-life-survivors (half-life=None, i.e. non-reverting, removed by default `min_half_life=1.0`), and in default non-FDR mode `_test_pair` already dropped p >= 0.10, so attached q-values are over p<0.10 survivors only and are strongly understated. `adf_pvalue_fdr` is also not in `PairResult` nor persisted, so "q-values always attached" never reaches the API/UI. Non-FDR mode also caps acceptance at 0.10 (cointegration.py:169) whatever `max_adf_pvalue` is. Fix: compute BH over every tested pair (including those rejected by correlation pre-filter), expose and persist the q-value. Bonferroni x2 (cointegration.py:166) itself is correct. | open |
| R-12 | P2 | backend/app/modules/screener/screener.py:467-476 | Net edge: arithmetic matches config (4 fills x (fee+slip) bps, funding over half-life, test_net_edge_arithmetic). But gross = entry_z x full-sample residual std, while the entry signal is the short-window rolling z (R-02), whose std is much smaller -> gross overstated; fee-notional assumes beta*pB ~ pA (wrong when alpha is large). Fix: use the same std as the signal; express costs on gross notional `pA + beta*pB`. | open |
| R-13 | P2 | backend/app/modules/screener/screener.py:488-496,208-211; intraday_monitor.py:143-147 | Composite score is incomparable across runs: `hurst_score=0` when `include_hurst` is False (default for `/run`, True for live screener) -> max 85 vs 100; live monitor ranks top-N by it. Screener itself sorts by `corr*(1-p)`, not composite. Fix: renormalise weights over available components; one sort key. Hurst estimator itself is correct (GHE on levels, verified by tests RW ~0.5, OU < 0.5). | open |
| R-14 | P2 | backend/app/modules/screener/intraday_monitor.py:158-160,187-200 | Monitor deliberately uses the forming 5m candle (`is_unusual` flickers within a bar) and `zscore_delta` subtracts the daily rolling OLS z from a Kalman innovation z: different statistics, delta meaningless. Fix: evaluate on the last closed candle (show live price separately); drop or redefine the delta. | open |
| R-15 | P2 | backend/app/api/routes.py:553-557; backtester.py:60-61 | Spread chart and backtester ignore the pair's `timeframe` (default `'1d'`) and assume daily bars in `min_required_points = lookback_days*0.8`; a pair screened on 1h/5m is charted/backtested on daily data. Fix: pass `pair['timeframe']`. | open |
| R-16 | P2 | backend/app/modules/screener/live_screener.py:50-110; api/routes.py:416-418 | DB restore omits `half_life`, `expected_net_edge_pct`, `timeframe` (blank columns after restart) and uses DB ids while fresh runs use `idx+1`; `get_pair_details`/spread match `id == pair_id or idx+1 == pair_id`, so after a restore a request can resolve to a different pair. Fix: restore all columns; single id scheme; drop the index fallback. | open |
| R-17 | P2 | backend/tests/test_screener.py:175-176; tests overall | `adf_pvalue_fdr >= adf_pvalue` is always true for BH (no signal). Missing tests for R-01..R-04 (forming bar, rolling-z bound, Kalman scale, /run field passthrough); no truncation (point-in-time) test for `current_zscore`. | open |
| R-18 | P2 | data_loader.py (21 `print`, 8 `except Exception: pass`), cointegration.py:173-175, data_loader.py:27-29,428-439; screener.py:412-424 | Slop/debt: print debris (incl. DEBUG prints for hard-coded symbols, data_loader.py:235-244), cointegration errors printed and swallowed as "not cointegrated", imports mid-module, duplicated double-check cache block, second OLS just to recover alpha that `engle_granger_test` already fits. Fix: logging, return alpha from the test, delete duplicates. | open |
| R-19 | P2 | backend/app/modules/screener/data_loader.py:81-197; README.md | Universe = today's top-volume listed perps; delisted names absent and assets with <80% history dropped. No survivorship statement and no "not investment advice" disclaimer anywhere (grep README/docs/frontend empty). Fix: state limitation + disclaimer in README and UI footer (pointer for design/docs). | open |
| R-20 | P2 | backend/app (mypy) e.g. api/routes.py:442-443 | `mypy app --ignore-missing-imports`: 77 errors in 8 files (family target: clean). Mostly SQLAlchemy `Column[Any]` passed into pydantic models. Fix: SQLAlchemy 2.0 `Mapped[]` typing or explicit casts. | open (acknowledged in STATE) |

## Correctness and quality
Finance checklist (rows that apply to a screener; backtester rows checked because the app ships one):
| Row | Result | Evidence |
|---|---|---|
| 1 No lookahead | FAIL | R-01 forming bar; R-07 full-sample beta fallback; R-09 same-close fill; screener z uses in-sample OLS (acceptable for a screener reading, not for a backtest) |
| 3 Costs | PARTIAL | net-edge formula matches config (R-12 caveats); backtester costs exist (QA BUG-8) but fills at decision close |
| 4 Multiple testing | PARTIAL | BH implemented, Bonferroni x2 correct; m shrunk + q-values hidden (R-11); FDR unreachable from UI (R-04) |
| 7 Sanity | n.a. | no headline result claimed |
| 8 Data: survivorship / adjusted prices / tz | PARTIAL | survivorship undisclosed (R-19); perps have no corporate actions (n.a.); timestamps are UTC ms -> naive UTC index (OK) |
| 9 Golden values | PASS | test_stats / test_calculator_metrics goldens pass |
Other areas checked:
- Hurst (hurst.py:38-65): correct GHE on levels; tests pass. Score direction (0.5-H)/0.5 correct.
- Beta semantics: price-level OLS A = alpha + beta*B, beta in units of B per A: consistent with position sizing `qty_b = beta*qty_a`; conflicts with the `beta > 10` caps (R-07). Note: plan T7 says "(log prices)" but code is price-level; STATE explains the decision.
- Kalman: filter equations correct (predict P+Q, gain, update); calibration wrong (R-03).
- Alerts/positions: R-05 plus QA BUG-1/3/4. Position PnL legs correct (QA goldens).
- Rate-limit/auth code (security.py): logic correct (constant-time compare, sliding window); scale/proxy issues in SECURITY S-03/S-06; `RateLimiter(name=...)` param unused (P3).
- Error handling: `str(e)` removed from 4xx/5xx details in diff; remaining leaks in `/health` and `/status` (SECURITY S-09). Broad `except Exception` returning empty results (routes.py:400-404, 516-524) hides failures as "0 pairs" (P2-level, folded into R-18).

AC walk (plan.md T2-T11): T2 auth/CORS/cron/rate limit - met (tests). T3 - met. T4 - met. T5 - per SECURITY. T6 - met per SECURITY. T7 Hurst/beta - Hurst met; beta kept price-level by decision. T8 live monitor - fetch/limit fix met; calibration broken (R-03). T9 tests - present but miss R-01..R-04 (R-17). T10 - tsc 0, ruff 0, mypy 77 (R-20). T11 docs - disclaimer missing (R-19). FDR opt-in claim - not reachable from UI (R-04). ACs (T2-T11): 6/10 fully met (T2-T7), 4 partial (T8, T9, T10, T11).

## Security
See `docs/SECURITY.md` (S-01..S-10, categories 10/10). Pointers from this pass, not new findings: cron blocking event loop = S-04; limiter on proxy IP = S-03; pickle cache = S-01.

## Design
Not done in this pass (design-reviewer out of scope). Required by router: screenshots at 375/768/1440, >= 2 rounds, ban check. Open.

## Final verification
Run by reviewer on 2026-10-25 (working tree incl. untracked QA tests; no fixes were applied, so this is the pre-fix baseline):
```
$ cd backend && PYTHONIOENCODING=utf-8 scratchpad/venv2/Scripts/python.exe -m pytest -q
88 passed, 5 xfailed, 5 warnings in 13.16s
  (before QA tests were added: 23 passed, 5 warnings in 6.20s)
$ scratchpad/venv/Scripts/mypy.exe app --ignore-missing-imports
app\api\routes.py:442: error: Argument "composite_score" to "PairResult" has incompatible type "Column[Any]"; expected "float | None"  [arg-type]
app\api\routes.py:443: error: Argument "current_zscore" to "PairResult" has incompatible type "Column[Any]"; expected "float | None"  [arg-type]
Found 77 errors in 8 files (checked 67 source files)
$ scratchpad/venv/Scripts/ruff.exe check app tests --config ../pyproject.toml
All checks passed!
$ cd frontend && npx tsc --noEmit
tsc exit 0
```
Ad-hoc evidence scripts (not committed): rolling-z bound (R-02) and Kalman scale (R-03) outputs quoted in the findings.
Production frontend build (`npm run build`) was not re-run in this pass.

## Not covered
- Design gate (375/768/1440, bans, a11y): not done.
- `npm run build` and Docker image build: not run.
- Live Binance behaviour (rate limits, full-universe scan time vs freshness SLA): not measured (QA measured a 6-asset scan only).
- `backend/app/data_layer/` package, Redis path, exports, `/calculate-position`, history analyzer: not reviewed beyond grep.
- Frontend logic beyond the settings -> API contract (R-04): not reviewed.
- Built-in `code-review` / `simplify` skills were not invoked; review done manually on the code.

## Trap-worthy (for known-traps.md)
- 2026-10-25 - **Rolling z-score over a tiny window is bounded**: with sample std over w points, |z_last| <= (w-1)/sqrt(w) (w=5 -> 1.79). A half-life-sized window can make the entry threshold unreachable. Use a floor of 20-30 bars or EWMA.
- 2026-10-25 - **Kalman hedge with absolute Q/R in price units** gives z that depends on the price level (cheap coins never alert, expensive pairs always alert). Normalise prices (log or /p0) or estimate R from residuals.
- 2026-10-25 - **Request schema narrower than the UI payload**: pydantic silently drops unknown fields, so new settings look wired but do nothing. Add a contract test per new setting (or `extra="forbid"`).
- 2026-10-25 - **Rank index as entity id**: alerts keyed by `idx+1` of the last scan move to another pair after the next scan. Key by natural id (asset pair).
- 2026-10-25 - **Auto-start-on-GET without failure backoff** turns a polled status endpoint into an exchange retry storm when the first run fails.
- 2026-10-25 - **Price cache keyed without time** (symbol+lookback) freezes a "live" screener on its first download.

# Handoff
status: active
date: 2026-11-03
from-chat-tokens: 250000

## Goal
Bring the crypto stat-arb pairs screener (FastAPI + React, finance/screener router) to release-ready. All 10 review P1 fixed; remaining work is P2/QA bugs, one security P1 needing an owner decision, and release blockers that need the owner. No push to main / PR merge / deploy / history rewrite without the owner's yes (pushing to chore/audit is allowed).

## State
- Done: audit, security hardening, deps pinned, Docker hardened, Hurst/FDR fixes, README+screenshots, framework docs, and (2026-11-03) R-01..R-10 fixed test-first, BUG-1, S-01, scan scheduler + /health freshness, compose log rotation + pinned images + secured datalayer compose, npm audit fix, UI disclaimer/llms.txt (see docs/STATE.md).
- Evidence: backend pytest 121 passed + 4 xfailed (BUG-3,5,6,7); frontend tsc 0 errors, `npm run build` ok; mypy 81 errors (`--ignore-missing-imports`); ruff (E9,F) 4 pre-existing F841; pip-audit clean; npm audit --omit=dev: 0 high, 5 moderate (react-query v3 chain); secrets-scan --history: 0 hits.
- Running: nothing.
- Branch: chore/audit, local commits on top of origin/chore/audit (1418090); see `git log`. Push to chore/audit is allowed; not main.

## Decisions
- beta 70/544 is a price-unit ratio, not a bug; backtester/spread chart no longer cap beta at 10.
- FDR is opt-in; q-values always attached.
- Kalman runs on first-value-normalised prices, R auto-estimated from warm-up OLS residuals (INTRADAY_KALMAN_R unset); Q stays absolute in normalised units (tying Q to R was tested: z calibrates but beta stops tracking). z std is still sub-unit.
- Backtester fills on the next bar's close; z-stop fires on the adverse side; no full-sample beta fallback (bars without 30 trailing bars are skipped).
- Alerts match results by (asset_a, asset_b), not rank id.
- Scheduler: in-process thread, `SCAN_SCHEDULER_ENABLED` (compose true), one attempt per `SCAN_INTERVAL_SECONDS`; /health 503 when last scan older than 2x interval.

## Next
1. Security: S-02 (nginx injects API_KEY for every client) once the owner picks the auth model; S-03 X-Forwarded-For + limiter; S-07 vite bump; replace pickle cache with data-only format.
2. QA bugs: BUG-3 alert cooldown, BUG-5 LiveScreener.start loop, BUG-6 overlapping scans, BUG-7 stale feed (remove xfail as each lands).
3. REVIEW P2 R-11..R-20 (BH over all tested pairs and expose q-value, net-edge std, composite renormalise, monitor closed candle, timeframe in spread/backtest, restore all DB columns, test gaps, print/except debt, mypy).
4. Release: B9 docker clean build + E2E smoke, B10 live monitor recheck on real Binance (use_fdr=false), design-reviewer gate (375/768/1440), remove stale deploy files after the host is chosen.

## Open questions
- Secrets: API_KEY, CRON_SECRET, REDIS_PASSWORD, POSTGRES_PASSWORD (.env, never in chat).
- Deploy target (VPS compose default), domain/TLS, CORS_ORIGINS.
- Alerts channel: Telegram/email or in-app only.
- Purge backend/data/stat_arb.db from git history (history rewrite)?
- LICENSE choice (none added).
- S-02: how to authenticate users in front of the frontend container.
- pip SSL (self-signed chain): `--trusted-host` was blocked; allow or fix certificates.

## Traps
- Cyrillic path breaks uv run; use the system Python / venv python directly.
- Tests share a rate limiter: conftest resets it per test.
- Heredocs in the shell mangle backslashes: build path-like strings with chr(92) in tests.
- Alerts check reads memory only when no DB session; pair_id (scan rank) is not stable.

## Verify
- `cd backend && python -m pytest -q` (121 passed, 4 xfailed)
- `cd frontend && npx tsc --noEmit && npm run build`
- `git status` clean on chore/audit

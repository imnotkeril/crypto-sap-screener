# Handoff
status: active
date: 2026-11-05
from-chat-tokens: 300000

## Goal
Bring the crypto stat-arb pairs screener (FastAPI + React, finance/screener router) to release-ready. Code work is essentially done; what remains is the full design gate, a few leftovers and release steps that need the owner. No push to main / PR merge / deploy / history rewrite without the owner's yes (pushing to chore/audit was allowed by the lead session).

## State
- Done: all 10 review P1, BUG-1/3/5/6/7 (0 xfail left), S-01 (JSON cache, symbol validation), S-02 (nginx allowlist, cron 404 via proxy), S-03, S-07 partial, R-11..R-13, R-15/16, R-18..R-20, scan scheduler + /health freshness, compose hardening, docker E2E smoke, light design review (see docs/STATE.md).
- Evidence: backend pytest 127 passed, 0 xfail; mypy clean (backend/mypy.ini documents ORM Column overrides); ruff F clean; frontend tsc 0, build ok; docker build of backend+frontend, real Binance scan inside the container (561 pairs tested, 3 found), /health, 401 without key, proxy 200, cron 404, live snapshot with Kalman z verified; pip-audit clean; npm: dev-server-only advisories (vite/esbuild) + react-query chain remain.
- Running: nothing (compose project audit-statarb stopped).
- Branch: chore/audit, fully pushed (origin/chore/audit = a700c21 as of 2026-11-09). PR #11 is open and mergeable, no CI checks configured on it. Not merged to main, not deployed anywhere (Vercel project `statistical-arbitrage-pairs-screener` exists but the app needs the compose backend, which has no host yet).

## Decisions
- beta 70/544 is a price-unit ratio, not a bug; no beta cap at 10 anywhere.
- FDR is opt-in; BH family now = all pairs passing the correlation screen; q-value exposed as adf_pvalue_fdr (not persisted).
- Kalman on first-value-normalised prices, R auto from warm-up residuals; Q absolute in normalised units; z dispersion still sub-unit.
- Backtester: next-bar fills, adverse-side z-stop, no full-sample beta fallback.
- Alerts match by (asset_a, asset_b) with a 15-min cooldown; DB alerts evaluated.
- S-02 default (flag for owner): nginx serves /api only to loopback, 172.16/12, 192.168/16 and FRONTEND_ALLOW_CIDR; cron path is 404 through the proxy; the proxy still injects API_KEY, so any public exposure needs real auth in front.
- Scheduler: SCAN_SCHEDULER_ENABLED (compose true), one attempt per SCAN_INTERVAL_SECONDS; /health 503 when last scan older than 2x interval.

## Next
1. Full design-reviewer gate with Playwright (docs/DESIGN_REVIEW.md is partial): keyboard, motion, Live monitor, Trends, pair detail; add a `<main>` landmark, mobile card layout for the pairs table.
2. Leftovers: R-14 (zscore_delta), R-15 backtester timeframe, R-17 stronger FDR test, BUG-2/4/8 (low), S-04 cost bounds, S-06, react-query v5, vite 7.
3. Release (owner-dependent): B1 history purge, B6 secrets/domain/TLS/CORS, B8 stale deploy files after host choice, Postgres dump/restore and datalayer container test, LICENSE.

## Open questions
- Secrets: API_KEY, CRON_SECRET, REDIS_PASSWORD, POSTGRES_PASSWORD (.env, never in chat).
- Deploy target (VPS compose default), domain/TLS, CORS_ORIGINS.
- Alerts channel: Telegram/email or in-app only.
- Purge backend/data/stat_arb.db from git history (history rewrite)?
- LICENSE choice (none added).
- S-02: keep the allowlist default or put SSO/VPN/auth_basic in front?
- pip SSL (self-signed chain): `--trusted-host` was blocked; allow or fix certificates.

## Traps
- Cyrillic path breaks uv run; use the system Python / venv python directly.
- Shell heredocs/sed mangle backslashes and line continuations (broke the Dockerfile once): use the Edit/Write tools for such files.
- Tests share a rate limiter and the /run flag: conftest resets both per test.
- Compose host ports clash with other audit projects: use a project name and an override file with high ports (see RUNBOOK / this session's override).

## Verify
- `cd backend && python -m pytest -q` (127 passed) and `python -m mypy app`
- `cd frontend && npx tsc --noEmit && npm run build`
- `git status` clean on chore/audit

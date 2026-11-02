# Handoff
status: active
date: 2026-11-02
from-chat-tokens: 300000

## Goal
Bring the crypto stat-arb pairs screener (FastAPI + React, finance/screener router) to release-ready. Framework pass done; code fixes from the review are still open. No push/PR/deploy without the owner's yes.

## State
- Done: audit, security hardening, deps pinned, Docker hardened, Hurst/FDR/live-monitor fixes, tests, README+screenshots, REVIEW/QA/SECURITY/RUNBOOK/RELEASE_CHECKLIST/RULES/AUDIT_DOCS (see docs/STATE.md).
- Evidence: backend pytest 88 passed + 5 xfailed; frontend tsc 0 errors, build ok; ruff (E9,F) clean; mypy 77 errors (`--ignore-missing-imports`) / 102 plain.
- Running: nothing (ports 28431/28432, container audit-statarb-shots stopped).
- Branch/commit: chore/audit @ 7b08588, tree clean. 18 local commits ahead of origin/main, NOT pushed (branch not on remote).

## Decisions
- beta 70/544 is a price unit ratio, not a bug - needed for sizing; test_stats pins it.
- FDR is opt-in (strict BH over all candidates returned 0 pairs on real data); q-values always in adf_pvalue_fdr.
- Code fixes for REVIEW P1 were deferred by the owner (scope = framework + docs only).

## Next
Fix order for the 10 open P1 (docs/REVIEW.md), tests first (5 strict xfails in backend/tests mark known bugs):
1. R-01 forming bar: data_loader.py:233-242,325-327 + screener.py current_zscore - drop last incomplete candle.
2. R-04 UI settings not sent: schemas.py ScreeningConfigRequest + routes.py /run - add fields. R-05 alerts keyed by rank id: alert_manager.py + screener.py id assignment (use stable pair key). Fix BUG-1 (alerts stored in SQLite never fire, routes_alerts.py:75-91 vs 219-224).
3. R-06 cold-start scan storm routes.py /status (backoff after failure). R-10 price cache TTL data_loader.py. R-02 rolling-z cap cointegration.py (min window). R-03 Kalman scale kalman.py/config (normalise by price level).
4. Backtester: R-07 full-sample beta fallback (backtester.py:149-172), R-08 inverted z-stop (:325,432), R-09 same-close fill (:500-513).
5. Release blockers (docs/RELEASE_CHECKLIST.md): B1 history/license scans + stat_arb.db in git history (owner decision); B2 periodic scan scheduler; B3 /health last-scan; B4 log rotation; B5 backup restore test; B6 secrets values, domain/TLS, host, CORS_ORIGINS; B7 rerun pip-audit/npm audit, mypy debt; B8 stale deploy files (docker-compose.datalayer.yml, vercel.json, railway/nixpacks) and image pins; B9 clean build + E2E + CHANGELOG upkeep; B10 live monitor recheck on real Binance (use_fdr=false).
Also: fix wrong file:line refs in REVIEW.md (A-04), /llms.txt, LICENSE, UI disclaimer.

## Open questions
- Deploy target (VPS compose recommended; Vercel unsuitable)? Purge backend/data/stat_arb.db from git history (needs history rewrite)? Telegram/email alerts wanted? Values for API_KEY, CRON_SECRET, REDIS_PASSWORD, POSTGRES_PASSWORD.

## Traps
- Cyrillic path breaks uv run; use venv python directly. pip here fails on SSL (self-signed chain); --trusted-host was blocked by the classifier - ask the owner, do not bypass.
- Scratchpad venvs got corrupted (uvicorn files missing): recreate or run backend via Docker image.
- Alerts check reads memory only; pair_id is a scan rank, not stable. Nginx frontend injects API_KEY for anyone reaching its port.

## Verify
- `cd backend && python -m pytest -q` (88 passed, 5 xfailed)
- `cd frontend && npx tsc --noEmit && npm run build`
- `git status` clean on chore/audit

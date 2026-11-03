# Changelog

## Unreleased (branch chore/audit, local only)
- Security: API key auth, CORS allowlist, cron secret, rate limits, no debug endpoint, no error detail leakage, pair_id validation.
- Dependencies bumped and pinned (fastapi 0.162.0, starlette 1.9.0, python-multipart 0.0.32, ...).
- Docker: non-root backend, healthchecks, ports on 127.0.0.1, required secrets, nginx frontend.
- Statistics: Hurst estimator fixed, FDR over all candidates (opt-in), Bonferroni x2 for two-direction Engle-Granger.
- Live monitor: explicit candle limit, fresh candles, snapshot cache.
- Frontend: tsc clean, vendor chunk split.
- Docs: README rewritten, RULES, REVIEW, QA, SECURITY, RUNBOOK, RELEASE_CHECKLIST.
- Fixed all 10 review P1s test-first (2026-11-03): forming candle dropped, UI settings reach /run, alerts keyed by (asset_a, asset_b) and DB alerts evaluated, cold-start scan backoff, price cache freshness, rolling-z window >= 20 bars, scale-invariant Kalman, backtester: no future beta, z-stop on the adverse side, next-bar fills.
- Ops: in-process scan scheduler, /health scan freshness (503 when stale), compose log rotation, pinned images, secured datalayer compose, npm audit fix.
- UI footer disclaimer, survivorship note in README, llms.txt.
- Tests: 112 passed, 4 xfailed (BUG-3, 5, 6, 7).
- Known open: P2 items in docs/REVIEW.md, docs/QA.md, docs/SECURITY.md, owner decisions in docs/HANDOFF.md.

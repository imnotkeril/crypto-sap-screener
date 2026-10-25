# Changelog

## Unreleased (branch chore/audit, local only)
- Security: API key auth, CORS allowlist, cron secret, rate limits, no debug endpoint, no error detail leakage, pair_id validation.
- Dependencies bumped and pinned (fastapi 0.162.0, starlette 1.9.0, python-multipart 0.0.32, ...).
- Docker: non-root backend, healthchecks, ports on 127.0.0.1, required secrets, nginx frontend.
- Statistics: Hurst estimator fixed, FDR over all candidates (opt-in), Bonferroni x2 for two-direction Engle-Granger.
- Live monitor: explicit candle limit, fresh candles, snapshot cache.
- Tests: 88 passed, 5 xfailed (known bugs). Frontend: tsc clean, vendor chunk split.
- Docs: README rewritten, RULES, REVIEW, QA, SECURITY, RUNBOOK, RELEASE_CHECKLIST.
- Known open: see docs/REVIEW.md (10 P1), docs/QA.md, docs/SECURITY.md.

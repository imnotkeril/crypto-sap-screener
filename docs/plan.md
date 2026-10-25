# Plan (finish after audit)

- [x] T1 adopt docs + WIP committed (check: git clean)
- [x] T2 auth (API key) + CORS allowlist + cron/run protection + rate limit
- [x] T3 remove /debug/db, stop leaking str(e)
- [x] T4 validate pair_id in alerts/positions
- [x] T5 bump fastapi/starlette/python-multipart/anyio/python-dotenv (pip-audit clean)
- [x] T6 compose: ports 127.0.0.1, env passwords, prod frontend build, non-root, healthcheck
- [x] T7 beta/Hurst regression (log prices) + tests
- [x] T8 live monitor fix
- [x] T9 tests: net-edge, FDR, Kalman, API smoke
- [x] T10 tsc/mypy/ruff clean, bundle code-split
- [x] T11 README/.env.example/docs, audit "After fixes"

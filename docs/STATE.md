# STATE

## Log
- 2026-10-24 audit done (docs/AUDIT_2026-10-24.md); WIP committed 7333b2e.

## Needed from owner
- Deploy target (Railway / VPS compose / Vercel+worker), domain/TLS, managed Postgres/Redis, secrets (API key value).
- Decision on purging backend/data/stat_arb.db from git history.
- 2026-10-24 T2-T9 done: auth/CORS/cron/rate-limit, deps pinned, docker hardened, Hurst+FDR fixed, live monitor fixed, 23 tests pass (backend). Beta 70/544 = unit ratio, not a bug.

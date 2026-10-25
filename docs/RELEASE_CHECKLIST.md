# RELEASE CHECKLIST (release-prep, devops) - 2026-10-25

Status: NOT ready to release. Nothing pushed/deployed. Items checked here are read-only; unticked = open.

## 1. Host choice
Recommendation: **self-hosted Docker Compose on one machine (local PC for personal use, or a small VPS like Hetzner CX22)**. Reasons: the product needs a long-lived process (live screener thread, intraday monitor, data layer with Binance WebSocket + Redis + Postgres), SQLite file state and in-memory alerts/rate limiter (single process). Railway works for the backend but is paid and needs managed Redis/Postgres; Vercel cannot run it fully.

## 2. Deploy files: consistent / stale / conflicting
| File | Verdict |
|---|---|
| `Dockerfile` | Consistent, current (non-root, HEALTHCHECK on /health, honors $PORT). Source of truth. |
| `docker-compose.yml` | Consistent, current (127.0.0.1 binding, required secrets, volumes, restart policy). `docker compose config -q` with dummy REDIS_PASSWORD/POSTGRES_PASSWORD/API_KEY: exit 0. Gaps: no log rotation, no cron/scheduler service, images use floating tags (`redis:7-alpine`, `postgres:15-alpine`, python:3.11-slim). |
| `docker-compose.datalayer.yml` | Stale/insecure: hardcoded `datalayer/datalayer` password, ports bound to 0.0.0.0 (no 127.0.0.1), obsolete `version:` key, no auth. Overlaps with the main compose (same ports/service names). Use only the main compose; delete or fix this one. |
| `railway.json`, `Procfile`, `nixpacks.toml`, `runtime.txt` | Backend-only Railway/Heroku path. Consistent with each other (`cd backend && uvicorn ... $PORT`) but conflicting: `railway.json` says builder DOCKERFILE while `nixpacks.toml` and `Procfile` imply Nixpacks; Railway uses only one. `nixpacks.toml` installs `requirements.txt` at root while `railway.datalayer.json` installs `backend/requirements.txt` (two requirements files: verify they match). No start-time health check configured in railway.json. |
| `railway.datalayer.json` | Consistent with RAILWAY_DATALAYER.md; NIXPACKS builder vs Docker for the rest, and relies on `backend/requirements.txt`. Mentions Supabase Postgres - not used anywhere else. |
| `vercel.json` (root) | **Conflicting.** Only defines a daily cron (`0 0 * * *`) to `/api/v1/screener/cron/run` - no builds/routes. Vercel serverless has an ephemeral filesystem (SQLite `data/stat_arb.db` is lost between invocations), no background threads (live screener/monitor/WebSocket data layer), in-memory alerts and rate limiter reset per instance, and a synchronous full scan may exceed function time limits. Vercel cron sends `Authorization: Bearer $CRON_SECRET` which the endpoint supports, but the whole path only makes sense if DATABASE_URL is an external Postgres and function timeout is sufficient. `backend/serverless_entry.py` exists for that mode. Treat Vercel as unsupported unless the owner picks it. Cron `0 0 * * *` also contradicts the 30-minute scan interval in code. |
| `frontend/vercel.json`, `frontend/railway.json`, `frontend/nixpacks.toml` | `frontend/nixpacks.toml` uses `npx serve`, but CLAUDE/STATE says `serve` was dropped (commit 598e116); `frontend/Dockerfile` + nginx template is the current path. Stale: nixpacks.toml (and RAILWAY_DEPLOYMENT.md "Option A"). `frontend/vercel.json` is fine for a static SPA but has no `/api` rewrite, so VITE_API_URL must point at a public backend. |
| `DEPLOYMENT_NO_DOCKER.md` | Mostly valid (systemd + nginx). Stale details: `.env` only lists DATABASE_URL (no API_KEY/REQUIRE_AUTH/CORS_ORIGINS), `--host 0.0.0.0` exposes 8000 directly (should be 127.0.0.1 behind nginx), nginx lacks TLS and X-API-Key injection (the compose frontend container proxies the key; plain static nginx would need the key in the browser). |
| `RAILWAY_DEPLOYMENT.md` | Stale: describes a past failed deploy, lists `npx serve`, only DATABASE_URL/PORT env, no API_KEY/CRON_SECRET (with REQUIRE_AUTH it would fail at start or run open). |
| `RAILWAY_DATALAYER.md` | Valid for the data layer; Option A references the stale datalayer compose; says "Vercel-hosted screener" which conflicts with the above. |

## 3. Env var table (names only, from `.env.example`)
| Name | Where | Notes |
|---|---|---|
| DATABASE_URL | backend | sqlite default; compose backend = sqlite in volume; datalayer = Postgres URL |
| REDIS_URL | backend, datalayer | compose injects it with password |
| DATA_LAYER_URL | backend | empty = direct ccxt |
| BINANCE_API_KEY, BINANCE_API_SECRET | backend | optional; public data needs none; read-only keys only, never live trading |
| SCREENER_MIN_CORRELATION, SCREENER_MAX_ADF_PVALUE, SCREENER_LOOKBACK_DAYS, SCREENER_MIN_VOLUME_USD, SCREENER_MAX_ASSETS | backend | tuning |
| INTRADAY_MONITOR_INTERVAL, INTRADAY_TOP_PAIRS, INTRADAY_ZSCORE_ALERT_THRESHOLD, INTRADAY_KALMAN_TIMEFRAME, INTRADAY_KALMAN_LOOKBACK_DAYS, INTRADAY_KALMAN_DELTA, INTRADAY_KALMAN_R | backend | live monitor |
| VITE_API_URL | frontend build | public backend URL for static hosting |
| API_KEY | backend + frontend container | required in prod |
| CRON_SECRET | backend | Bearer for `/cron/run` |
| REQUIRE_AUTH | backend | must be true in prod (compose sets it) |
| CORS_ORIGINS | backend | set to the real frontend origin |
| AUTO_SCREEN_ON_COLD_START | backend | |
| REDIS_PASSWORD, POSTGRES_PASSWORD | compose only | required by compose |
Not in `.env.example` but used by compose/data layer: PORT, DATALAYER_SYMBOLS, DATALAYER_TIMEFRAMES, DATALAYER_HISTORY_START (add as comments). Notification vars (Telegram token/chat id, SMTP, VAPID): none exist.

## 4. Module inserts
**background-jobs**
- [ ] Worker deployment defined: no dedicated worker; scans are in-process. Periodic loop is not started on boot (`LiveScreener.start()` is never called at startup; only `/status` cold start, `/run-live`, `/cron/run`). Need a scheduler (see B2).
- [x] `CRON_SECRET` present in `.env.example` and compose; INNGEST_* not used (not applicable); `DATABASE_URL` present.
- [x] Restart policy known (`unless-stopped`; Railway ON_FAILURE x10); log access `docker compose logs`.
- [x] Runbook line "retry/clear failed jobs": in RUNBOOK.md (no queue; re-trigger scan, restart backend if flag stuck).

**notifications**
- Gap: alerts are in-app only (in-memory `AlertManager`, lost on restart). No Telegram bot, email or web push exists, so bot token, owner chat id, VAPID keys, email domain, privacy-policy mention are N/A until the feature exists. Owner decision needed (N1): add Telegram notifications (z-score threshold + failed/stale scan) or accept in-app only.

## 5. Observability
- `/health` (no auth) reports process up + `screener_running` + `pairs_found` only; **no last-successful-scan timestamp**, and it returns "healthy" even on internal exception. Staleness is only visible via authenticated `/api/v1/screener/status` (`last_session.completed_at`, `last_error`). No alert on staleness exists. Product-code change needed (B3), out of scope for this step.
- Docker HEALTHCHECK exists for backend only (not frontend/datalayer).
- Logging: stdlib loggers, no rotation configured, no structured config; no `error-monitoring` module.

## 6. Release blockers
- [ ] B1 Secrets in git history: `backend/data/stat_arb.db` was committed earlier (STATE: owner decision pending on purge). `node scripts/secrets-scan.mjs --project . --history` and `license-check` not yet run in this step (no scripts executed here); required before release. History rewrite needs the user's yes.
- [ ] B2 No scheduler: add a compose service/host cron/Task Scheduler that calls `/cron/run` every 30 min (or start the loop at app startup). Without it data goes stale after the first scan.
- [ ] B3 Health endpoint lacks last-successful-scan; add `last_screening_time` / `last_session.completed_at` and a 503 when stale; wire an external uptime check.
- [ ] B4 Log rotation missing in compose.
- [ ] B5 Backup/restore commands in RUNBOOK are untested; run once on a copy and record.
- [ ] B6 Pending decisions from owner: deploy target; domain/TLS; actual values for API_KEY, CRON_SECRET, REDIS_PASSWORD, POSTGRES_PASSWORD; CORS_ORIGINS for the real origin.
- [ ] B7 Dependency audit from AUDIT_2026-10-24 ("After fixes" section says deps pinned; re-run `pip-audit`, `npm audit --omit=dev` and attach output); mypy 77 errors remain (non-blocking).
- [ ] B8 Cleanup/deconflict deploy files (datalayer compose insecure defaults, stale RAILWAY_DEPLOYMENT.md, frontend/nixpacks.toml, vercel.json) and pin Docker image versions.
- [ ] B9 Final clean-install build + tests + E2E smoke output, README quickstart re-run, version/CHANGELOG (no CHANGELOG found).
- [ ] B10 Re-check live monitor on real Binance (STATE note).

Non-blockers: notifications gap (N1) if the owner accepts in-app alerts; legal/SEO not applicable (private tool, no public site) unless made public.

## 7. Only the user can do
Choose host; provide secret values in `.env`; domain/DNS/TLS; decide on notifications; decide on history purge; approve push/deploy.

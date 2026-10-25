# RUNBOOK - Statistical Arbitrage Pairs Screener

Recommended host: **single machine with Docker Compose** (local PC or a VPS such as Hetzner), all ports bound to 127.0.0.1, TLS reverse proxy in front if public. See RELEASE_CHECKLIST.md for why not Vercel.

Placeholders: `$API_KEY`, `$CRON_SECRET` come from `.env` (never print or commit them). Backend = http://127.0.0.1:8000, data layer = :8001, frontend = :3100.

## Start / stop / restart
Prereq: `.env` in repo root with `REDIS_PASSWORD`, `POSTGRES_PASSWORD`, `API_KEY` (compose refuses to start without them), optional `CRON_SECRET`.

```bash
docker compose up -d --build        # start all (redis, postgres, datalayer, backend, frontend)
docker compose ps                   # status + healthcheck (backend has HEALTHCHECK on /health)
docker compose restart backend      # restart one service
docker compose stop                 # stop, keep volumes
docker compose down                 # remove containers, KEEP volumes
# NEVER: docker compose down -v     # deletes app-backend-data (SQLite), app-postgres, app-redis
```
Supervision: `restart: unless-stopped` on every service; Docker daemon must start on boot (Docker Desktop "start on login" on Windows; `systemctl enable docker` on Linux). No-Docker alternative: systemd unit from `DEPLOYMENT_NO_DOCKER.md` (`Restart=always`).

Windows port note: ports 6379/5432/8000/8001/3100 are shared with other local projects. Check `docker ps` / `netstat -ano | findstr :8000` before `up`.

## Logs and rotation
```bash
docker compose logs -f --tail=200 backend
```
Compose does NOT configure log rotation (default json-file driver grows unbounded). Fix before long-running use: add to each service
`logging: {driver: json-file, options: {max-size: "10m", max-file: "5"}}` (or set it globally in `/etc/docker/daemon.json`). Not done yet - tracked as blocker B4. systemd variant: journald rotates by itself.

## Health and "stale data" check
- `GET /health` (no auth): returns `{"status":"healthy","screener_running":bool,"pairs_found":int}`. **It does NOT expose last successful scan time**, and returns "healthy" even if the screener raised. It only proves the process is up.
- `GET /api/v1/screener/status` (header `X-API-Key: $API_KEY`): returns `last_session.completed_at`, `last_session.status`, `total_pairs_in_db`, `last_error`. This is the source for staleness.
```bash
curl -s -H "X-API-Key: $API_KEY" http://127.0.0.1:8000/api/v1/screener/status
```
Stale = `last_session.completed_at` older than ~2 hours (the in-code interval is 30 min, but see "Scans" - nothing schedules scans by default), or `last_error` non-null, or `last_session` null.
Data layer: `curl http://127.0.0.1:8001/health`. If it is down the live monitor falls back to direct ccxt/Binance (rate-limit risk).

## Scans: how they run, trigger, retry
Important: the periodic loop (`LiveScreener.start()`, every 1800 s) is NOT started at app startup. A scan runs only when (a) `GET /status` finds no session ever and `AUTO_SCREEN_ON_COLD_START=true`, (b) someone calls `POST /api/v1/screener/run-live`, or (c) an external scheduler hits the cron endpoint. So with Docker Compose you must add a scheduler (blocker B2).

Trigger now (background, returns immediately; 400 if already running):
```bash
curl -X POST -H "X-API-Key: $API_KEY" http://127.0.0.1:8000/api/v1/screener/run-live
```
Trigger synchronously (waits for completion; returns 500 on failure; rate-limited 6/min):
```bash
curl -H "Authorization: Bearer $CRON_SECRET" http://127.0.0.1:8000/api/v1/screener/cron/run
```
Retry a failed scan: read `last_error` from /status, fix cause (usually Binance rate limit/network: wait a few minutes), call the trigger again. There is no job queue, so there are no "failed jobs" to clear; state is one in-memory scan flag. If `is_running` is stuck true (crashed thread) -> `docker compose restart backend`. Note: the cron endpoint returns `completed` even when it skipped because a scan was already running.
Live intraday monitor: `routes_live.py` start endpoint (`/api/v1/live/...`), also manual; not auto-started and not restored after restart.

## Rotate API_KEY / CRON_SECRET
1. Generate a new value locally (e.g. `python -c "import secrets;print(secrets.token_urlsafe(32))"`), do not paste it into chat or logs.
2. Edit `.env` (API_KEY used by backend AND frontend proxy container).
3. `docker compose up -d backend frontend` (env is read at start; restart is required).
4. Update every external caller (cron scheduler, scripts). Verify old key returns 401, new one 200.
5. If the old key ever leaked: also check `git log` for it (see blocker B1 about history).

## Backups and restore
State that matters: SQLite file in volume `app-backend-data` (`/app/backend/data/stat_arb.db`: sessions, pair results, snapshots), Postgres volume `app-postgres` (data layer candles; re-creatable by backfill, lower value), Redis `app-redis` (cache, disposable). Alerts are in memory only and are lost on restart.
```bash
# SQLite backup (consistent copy via sqlite3 inside the container; use any path on host)
docker compose exec backend python -c "import sqlite3;s=sqlite3.connect('data/stat_arb.db');d=sqlite3.connect('data/backup.db');s.backup(d);d.close()"
docker compose cp backend:/app/backend/data/backup.db ./backups/stat_arb-$(date +%F).db
# Postgres backup
docker compose exec -T postgres pg_dump -U datalayer datalayer | gzip > backups/datalayer-$(date +%F).sql.gz
# Postgres restore
gunzip -c backups/datalayer-YYYY-MM-DD.sql.gz | docker compose exec -T postgres psql -U datalayer datalayer
# SQLite restore: docker compose stop backend; copy file into the volume as data/stat_arb.db; start backend
```
Restore NOT yet tested (blocker B5). Schedule daily via cron / Task Scheduler and keep copies off the machine.

## Notifications
In-app alerts only (in-memory `AlertManager`, UI). No Telegram/email/push: nobody is notified when a z-score threshold is crossed or when a scan fails. Gap, see RELEASE_CHECKLIST.md B3/N1.

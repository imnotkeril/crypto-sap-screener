# Market Data Layer - Deployment

The data layer (`backend/app/data_layer/`) is a persistent service - it
keeps a WebSocket connection open to Binance, runs backfill, and serves
candles/ticker/indicators over HTTP. This **cannot run on Vercel**
(serverless functions can't hold long-lived connections or background
loops).

## Option A: Run locally with Docker (free)

A self-contained `docker-compose.datalayer.yml` is provided at the repo
root, including its own Redis and Postgres containers - no external
services or paid hosting required:

```bash
docker compose -f docker-compose.datalayer.yml up -d --build
```

Then check `http://localhost:8001/health`. Data is persisted in Docker
volumes (`datalayer-redis`, `datalayer-postgres`) across restarts.

To point the screener at it, set `DATA_LAYER_URL=http://localhost:8001`
(or the container's address, e.g. `http://datalayer:8001` if the screener
also runs in Docker on the same network) as an env var on the main backend
process. When set, the live intraday monitor
(`backend/app/modules/screener/intraday_monitor.py`) reads ticker prices
from the data layer's Redis-backed cache instead of calling Binance via
ccxt on every request. If the data layer is unreachable, it falls back to
the direct ccxt call automatically.

## Option B: Railway (paid)

Runs as its own Railway service alongside the existing backend API
service.

## Setup (Railway)

1. In Railway, create a **new service** in the same project, pointing at
   this repository (same repo as the existing backend service).
2. Set **Config file path** to `railway.datalayer.json` (Railway dashboard ->
   service Settings -> Config-as-code).
3. Add a **Redis** plugin/service to the project if one doesn't already
   exist, and set `REDIS_URL` on this service to its connection string.
4. Set `DATABASE_URL` to the same Supabase Postgres URL used by the main
   backend (candles are stored in a separate `data_layer_candles` table, so
   it's safe to share the database).
5. Optionally override defaults via env vars:
   - `DATALAYER_SYMBOLS` - comma-separated, e.g. `BTC/USDT,ETH/USDT,SOL/USDT`
   - `DATALAYER_TIMEFRAMES` - comma-separated, e.g. `1m,5m,15m,1h,4h,1d`
   - `DATALAYER_HISTORY_START` - backfill start date, e.g. `2023-01-01`

## Health check

`GET /health` on the service's Railway-assigned domain returns the
configured exchange/symbols/timeframes once the pipeline has started.

## Consuming from the screener

The Vercel-hosted screener can call this service's HTTP API instead of
hitting Binance directly:

- `GET /ticker?symbol=BTC/USDT`
- `GET /candles/latest?symbol=BTC/USDT&timeframe=1m&limit=100`
- `GET /candles?symbol=BTC/USDT&timeframe=1h&start=2024-01-01T00:00:00Z`
- `GET /indicators?symbol=BTC/USDT&timeframe=1h`

Set an env var (e.g. `DATA_LAYER_URL`) on the screener service pointing at
this service's Railway domain to wire it up.

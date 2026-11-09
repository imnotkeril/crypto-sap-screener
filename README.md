# Statistical Arbitrage Pairs Screener (crypto-sap-screener)

[![CI](https://github.com/imnotkeril/crypto-sap-screener/actions/workflows/ci.yml/badge.svg)](https://github.com/imnotkeril/crypto-sap-screener/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Python 3.11](https://img.shields.io/badge/python-3.11-blue)
![React 18](https://img.shields.io/badge/react-18-61dafb)

A crypto pairs screener for statistical arbitrage. It loads Binance USDT futures prices through [ccxt](https://github.com/ccxt/ccxt), tests pairs of assets for cointegration, ranks them by a composite score that includes expected net edge after costs, and tracks the intraday z-score of the top pairs with a Kalman-filter hedge ratio. Results are shown in a React dashboard and served by a FastAPI API.

> **Disclaimer.** This is a research and educational tool. It is not investment advice. Statistical tests, backtests and simulated results do not guarantee future performance, and trading can lose all capital. The software **never sends orders** to any exchange. It has no order-placement code path and no live trading keys are used.
>
> **Survivorship bias.** The universe is today's top-volume listed Binance perpetuals: delisted assets are absent and assets with under 80% of the requested history are dropped, so results look better than a point-in-time universe would.

## What it does

- **Screens** the top Binance USDT futures by volume for pairs with high correlation, Engle-Granger cointegration (tested in both directions, Bonferroni-adjusted), a mean-reversion half-life and an expected net edge after fees, slippage and funding. Formulas: [`docs/RULES.md`](docs/RULES.md).
- **Monitors** the top daily pairs intraday: re-fits the hedge ratio with a Kalman filter on 5-minute candles and flags unusual z-scores.
- **Alerts**: z-score thresholds per pair are stored in the database and evaluated by `/api/v1/alerts/triggered/check`, with a 15-minute cooldown. Alerts are in-app only: nothing is sent to Telegram or email.
- **Tracks positions** as bookkeeping records (entry prices, quantities, PnL). Nothing is sent to an exchange.
- **Backtests** a z-score entry/exit strategy on one pair, with transaction costs and rolling hedge ratios.
- **Calculates** position sizes for a pair (dollar-neutral, equal-dollar and always-long-A or always-long-B).
- **Exports** results to CSV and Excel and keeps a history of screening sessions.

Included but separate: a **market data layer** (`backend/app/data_layer`), a standalone service that streams Binance prices into Redis and PostgreSQL. The screener does not depend on it (see [Known limitations](#known-limitations)).

## Screenshots

Taken on a local stack with real Binance data (1d scan, 1035 pairs tested, 3 found).

| | |
|---|---|
| ![Screener results](docs/img/screener.png) | ![Pair details](docs/img/pair-details.png) |
| Screener: ranked pairs, correlation matrix | Pair details: z-score, beta, Hurst, spread stats |
| ![Live monitor](docs/img/live-monitor.png) | ![Backtest](docs/img/backtest-results.png) |
| Live monitor: intraday z-score with Kalman hedge | Backtest of a z-score strategy on one pair |

## Stack

- Backend: Python 3.11, FastAPI, SQLAlchemy 2 (SQLite by default), pandas, numpy, statsmodels, scipy, ccxt, Pydantic Settings.
- Data layer: FastAPI, asyncpg (PostgreSQL), redis-py, websockets.
- Frontend: React 18, TypeScript, Vite 7, Tailwind CSS 3, Recharts, TanStack Query 5, axios.
- Tests: pytest (backend), TypeScript compiler (frontend).

## Repository layout

```
.
├── backend/
│   ├── app/
│   │   ├── main.py                 FastAPI app, CORS, routers, startup (init_db)
│   │   ├── config.py               Settings (environment variables, see below)
│   │   ├── database.py             SQLAlchemy models, init_db, additive column upgrade
│   │   ├── api/                    HTTP layer: routes.py (screener), routes_alerts.py,
│   │   │                           routes_backtester.py, routes_positions.py, routes_live.py,
│   │   │                           schemas.py, security.py (auth, rate limit), validation.py
│   │   ├── modules/                Business logic (see "Modules")
│   │   │   ├── screener/           cointegration, correlation, hurst, kalman, screener,
│   │   │   │                       live_screener, intraday_monitor, data_loader
│   │   │   ├── alerts/             alert_manager.py
│   │   │   ├── positions/          position_manager.py
│   │   │   ├── backtester/         backtester.py, strategy.py, metrics.py
│   │   │   ├── calculator/         position_calculator.py
│   │   │   ├── history/            history_analyzer.py
│   │   │   └── shared/             models.py (ScreeningConfig and other shared models)
│   │   └── data_layer/             Market data service (see "Market data layer")
│   ├── tests/                      pytest suite (conftest.py + 8 test modules)
│   ├── run.py                      Dev entry point (uvicorn with reload, port 8000)
│   ├── serverless_entry.py         Entry point for Vercel's Python runtime
│   ├── requirements.txt            Pinned runtime dependencies
│   ├── data/                       SQLite database (created at runtime)
│   └── cache/                      Pickled price cache (created at runtime)
├── frontend/
│   ├── src/                        App.tsx, components/ (dashboards, charts, tables), services/api.ts
│   ├── vite.config.ts              Dev server on 5173, /api proxy to the backend
│   ├── nginx.conf.template         Production proxy used by the frontend Docker image
│   └── Dockerfile
├── docs/                           RULES.md, QA.md, SECURITY.md, RUNBOOK.md, plan/state files, img/ (screenshots)
├── .github/workflows/ci.yml        CI: backend tests + ruff, frontend typecheck and build
├── LICENSE, SECURITY.md            MIT license, vulnerability reporting policy
├── .env.example                    Every variable the backend reads (names and comments only)
├── docker-compose.yml              Full stack: redis, postgres, datalayer, backend, frontend
├── docker-compose.datalayer.yml    Data layer with its own redis and postgres
├── Dockerfile                      Backend image (also used by the data layer)
├── Procfile, nixpacks.toml, railway.json, railway.datalayer.json, vercel.json, RAILWAY_*.md, DEPLOYMENT_NO_DOCKER.md
├── package.json                    Root scripts: dev (backend + frontend via concurrently)
└── pyproject.toml                  Project metadata and ruff/Vercel settings
```

## Quickstart

Requirements: Python 3.11 (the Dockerfile and `runtime.txt` pin 3.11), Node.js 18 or newer (the frontend Docker image uses Node 22), npm.

```bash
# 1. Backend dependencies
pip install -r backend/requirements.txt

# 2. Frontend dependencies
cd frontend && npm install && cd ..

# 3. Optional: configuration (no keys are needed for public market data)
cp .env.example backend/.env

# 4. Start both servers (root script, needs the root npm install for concurrently)
npm install
npm run dev
```

Then open http://localhost:5173. The API is at http://localhost:8000 and its interactive docs at http://localhost:8000/docs.

To run the two servers separately:

```bash
# Backend (terminal 1)
cd backend
python -m uvicorn app.main:app --port 8000

# Frontend (terminal 2)
cd frontend
npm run dev
```

The first screening run can take several minutes because it downloads candles for up to 100 assets. Click **Run Screening** in the dashboard, or call `POST /api/v1/screener/run`.

### Scripts

| Where | Command | What it does |
|---|---|---|
| root | `npm run dev` | Starts `backend/run.py` (uvicorn with reload, 127.0.0.1:8000) and the Vite dev server (5173) |
| root | `npm run install:all` | `pip install -r backend/requirements.txt` and `npm install` in `frontend/` |
| backend | `python -m uvicorn app.main:app --port 8000` | Production-style API server (no reload) |
| backend | `pip install pytest && python -m pytest -q` | Backend tests (pytest is not in `requirements.txt`) |
| backend | `python -m app.data_layer.main` | Market data layer service (port 8001, needs Redis and PostgreSQL) |
| frontend | `npm run dev` | Vite dev server on port 5173, proxies `/api` to `VITE_BACKEND_URL` or `http://localhost:8000` |
| frontend | `npm run build` | `tsc --noEmit` then `vite build` into `frontend/dist` |
| frontend | `npx tsc --noEmit` | Type check only |

## Configuration

Copy `.env.example` to `backend/.env` (the backend reads `.env` from its working directory). Never commit real values. The names below match the names in `.env.example` and `backend/app/config.py`.

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./data/stat_arb.db` | SQLAlchemy URL. Use `postgresql://...` on a server. |
| `REDIS_URL` | `redis://localhost:6379` | Read by the config only. The screener API does not use Redis. |
| `DATA_LAYER_URL` | empty | Read by the config only. The live monitor does not use it (see Known limitations). |
| `BINANCE_API_KEY` | empty | Optional. Public market data works without keys. Do not enable withdrawals on any key. |
| `BINANCE_API_SECRET` | empty | Optional, paired with `BINANCE_API_KEY`. |
| `SCREENER_MIN_CORRELATION` | `0.80` | Minimum Pearson correlation of returns. |
| `SCREENER_MAX_ADF_PVALUE` | `0.10` | Maximum Engle-Granger (Bonferroni-adjusted) p-value. |
| `SCREENER_LOOKBACK_DAYS` | `365` | History used for the daily screen. |
| `SCREENER_MIN_VOLUME_USD` | `1000000` | Minimum 24h USDT volume for an asset to be considered. |
| `SCREENER_MAX_ASSETS` | `100` | Top N assets by volume to screen. |
| `INTRADAY_MONITOR_INTERVAL` | `15` | Seconds during which a computed live snapshot is reused. |
| `INTRADAY_TOP_PAIRS` | `20` | Number of top daily pairs tracked intraday. |
| `INTRADAY_ZSCORE_ALERT_THRESHOLD` | `2.5` | Absolute z-score that marks a live pair as unusual. |
| `INTRADAY_KALMAN_TIMEFRAME` | `5m` | Candle timeframe for the intraday Kalman re-fit. |
| `INTRADAY_KALMAN_LOOKBACK_DAYS` | `3` | History fed to the Kalman filter. |
| `INTRADAY_KALMAN_DELTA` | `1e-4` | Kalman state transition parameter (hedge ratio agility). |
| `INTRADAY_KALMAN_R` | `1e-3` | Kalman observation noise variance. |
| `API_KEY` | empty | When set, every `/api/v1` route except the cron route requires header `X-API-Key`. Empty means open (development only). |
| `CRON_SECRET` | empty | Bearer secret for `GET/POST /api/v1/screener/cron/run` (`Authorization: Bearer <secret>`). |
| `REQUIRE_AUTH` | `false` | `true` makes startup fail when `API_KEY` is empty. |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173,http://localhost:3100` | Comma-separated allowed browser origins. |
| `AUTO_SCREEN_ON_COLD_START` | `true` | When no session has ever run, `GET /status` starts a background screen (this calls Binance). |
| `VITE_API_URL` | empty | Frontend build-time API base URL (put in `frontend/.env`). |
| `VITE_BACKEND_URL` | `http://localhost:8000` | Read by the Vite dev proxy (not in `.env.example`). |
| `API_KEY` (frontend dev) | empty | Read by the Vite dev proxy and added to proxied requests (not bundled into the build). |
| `REDIS_PASSWORD` | none | docker-compose only. Required. |
| `POSTGRES_PASSWORD` | none | docker-compose only. Required. |
| `PORT` | `8000` (backend) / `8001` (data layer) | Used by Docker images, Procfile and the data layer entry point. |

Market data layer (`backend/app/data_layer/core/config.py`, not listed in `.env.example`). Each list value must be a JSON array, not a comma-separated string (see Known limitations):

| Variable | Default | Meaning |
|---|---|---|
| `EXCHANGE` | `binance` | Only `binance` is implemented. |
| `DATALAYER_SYMBOLS` | `["BTC/USDT","ETH/USDT","SOL/USDT","BNB/USDT","XRP/USDT"]` | Symbols to stream, normalized form. |
| `DATALAYER_TIMEFRAMES` | `["1m","5m","15m","1h","4h","1d"]` | Candle timeframes. |
| `DATALAYER_HISTORY_START` | `2023-01-01` | Backfill start date (UTC). |
| `DATALAYER_REDIS_CANDLE_LIMIT` | `500` | Candles kept per symbol and timeframe in Redis. |
| `DATALAYER_TICKER_TTL` | `10` | Ticker cache TTL in seconds. |
| `DATALAYER_BACKFILL_CONCURRENCY` | `10` | Parallel REST backfill requests. |
| `DATALAYER_WS_BACKOFF_MIN` / `DATALAYER_WS_BACKOFF_MAX` | `1.0` / `60.0` | WebSocket reconnect backoff in seconds. |
| `DATALAYER_WS_HEARTBEAT_INTERVAL` | `20.0` | WebSocket heartbeat in seconds. |
| `DATALAYER_FUNDING_POLL_INTERVAL` | `300` | Reserved, not implemented. |
| `BINANCE_REST_URL` | `https://api.binance.com` | Binance REST base URL. |
| `BINANCE_WS_URL` | `wss://stream.binance.com:9443` | Binance WebSocket base URL. |
| `REDIS_URL` | `redis://localhost:6379` | Redis, required at startup. |
| `DATABASE_URL` | `sqlite:///./data/stat_arb.db` | Must be a `postgresql://` URL for the data layer (asyncpg). The SQLite default does not work for it. |
| `PORT` | `8001` | HTTP port of the data layer. |

## Modules

Business logic lives in `backend/app/modules`. The API layer in `backend/app/api` calls these modules.

| Module | Purpose |
|---|---|
| `screener` | Daily pair screening (`screener.py`), cointegration and half-life (`cointegration.py`), correlation (`correlation.py`), generalized Hurst exponent (`hurst.py`), Kalman hedge (`kalman.py`), Binance data loading and cache (`data_loader.py`), in-memory live screener (`live_screener.py`), intraday z-score monitor (`intraday_monitor.py`). |
| `alerts` | Z-score threshold alerts (`alert_manager.py`). In-app only. |
| `positions` | Position records and PnL (`position_manager.py`). Bookkeeping only. |
| `backtester` | Z-score strategy backtest (`backtester.py`, `strategy.py`) and metrics: Sharpe, drawdown, win rate, profit factor, Kelly, return/MAE (`metrics.py`). |
| `calculator` | Position sizing for a pair (`position_calculator.py`). |
| `history` | Metric changes between sessions, trend analysis and degradation detection across screening sessions (`history_analyzer.py`). |
| `shared` | Shared models, including `ScreeningConfig` with the cost model, FDR and clustering options. |

### Market data layer

`backend/app/data_layer` is a separate FastAPI service, started with `python -m app.data_layer.main` from `backend/` (port 8001). At startup it connects to Redis and PostgreSQL, then runs the ingestion pipeline as a background task.

| Package | Purpose |
|---|---|
| `ingestion` | Binance REST client, WebSocket manager with reconnect backoff, source adapters (`sources/binance.py`). |
| `normalization` | Symbol mapping, normalization and validation of raw candles and tickers. |
| `processing` | Indicator computation (`indicators.py`). |
| `storage` | `postgres_store.py` (historical candles, asyncpg) and `redis_store.py` (live tickers and recent candles). |
| `backfill` | Gap detection, buffered backfill and the backfill manager. |
| `core` | Settings, models, exceptions and the pipeline that wires the packages together. |
| `serving` | HTTP query API (`api.py`), query layer (`query_api.py`), pub/sub (`pubsub.py`). |

Data layer endpoints (served on port 8001, not part of the main API):

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Health check |
| GET | `/ticker?symbol=` | Latest ticker for a symbol |
| GET | `/candles/latest?symbol=&timeframe=&limit=` | Latest candles (limit up to 500) |
| GET | `/candles?symbol=&timeframe=&limit=` | Candles over a range (limit up to 10000) |
| GET | `/indicators?symbol=&timeframe=` | Indicators for a symbol and timeframe |

### Live intraday monitor

The monitor runs on demand, not as a background loop. Each `GET /api/v1/live/snapshot` recomputes the snapshot if the last one is older than `INTRADAY_MONITOR_INTERVAL` seconds. For each of the top daily pairs it fetches recent candles, re-fits the hedge ratio with the Kalman filter and computes the innovation z-score. Snapshots are stored in the `intraday_snapshots` table (kept for 6 hours). Formulas: [`docs/RULES.md`](docs/RULES.md) section 11.

## API

All routes are under `/api/v1` except `/`, `/health` and `/docs`. The list below is generated from the application's OpenAPI schema (`app.openapi()`): **37 operations on 31 paths**. Every `/api/v1` route requires header `X-API-Key` when `API_KEY` is set, except the cron route, which accepts `CRON_SECRET` or the API key. The data layer routes are listed in the Modules section.

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Service name, version and mode (no auth) |
| GET | `/health` | Health check with screener status (no auth) |
| GET | `/api/v1/screener/status` | Screener status and last session; may start a cold-start screen |
| POST | `/api/v1/screener/run` | Start a screening session in the background with a config body |
| POST | `/api/v1/screener/run-live` | Start the live screener in the background (fetches fresh data) |
| GET | `/api/v1/screener/results` | Current results with filters (correlation, beta, spread std, session) and sorting |
| GET | `/api/v1/screener/pairs/{pair_id}` | Details of one pair from the current results |
| GET | `/api/v1/screener/pairs/{pair_id}/spread` | Spread and z-score series for charting |
| GET | `/api/v1/screener/pairs/{pair_id}/history` | One pair across screening sessions |
| GET | `/api/v1/screener/pairs/history` | History of one pair by asset symbols (`asset_a`, `asset_b`) |
| GET | `/api/v1/screener/sessions` | Persisted screening sessions |
| GET | `/api/v1/screener/stats` | Summary statistics of the current results |
| GET | `/api/v1/screener/trends` | Trends across screening sessions |
| GET | `/api/v1/screener/comparison` | Current results compared with the previous session |
| GET | `/api/v1/screener/export/csv` | Export results to CSV |
| GET | `/api/v1/screener/export/excel` | Export results to Excel |
| GET | `/api/v1/screener/pairs/{pair_id}/export` | Export one pair (`format` parameter) |
| POST | `/api/v1/screener/calculate-position` | Position sizes for a pair from beta and capital |
| GET | `/api/v1/screener/cron/run` | Synchronous screening run for schedulers (`CRON_SECRET` bearer) |
| POST | `/api/v1/screener/cron/run` | Same as GET (both methods are registered) |
| GET | `/api/v1/alerts/` | List alerts, optional `pair_id` filter |
| POST | `/api/v1/alerts/` | Create an alert (`pair_id`, `asset_a`, `asset_b`, thresholds) |
| GET | `/api/v1/alerts/{alert_id}` | Get one alert |
| PUT | `/api/v1/alerts/{alert_id}` | Update thresholds or enabled flag |
| DELETE | `/api/v1/alerts/{alert_id}` | Delete an alert |
| GET | `/api/v1/alerts/triggered/check` | Check alerts against current results |
| POST | `/api/v1/backtester/run` | Run a z-score backtest for a pair (body: `BacktestRequest`) |
| GET | `/api/v1/backtester/results/{session_id}` | Backtest results by session |
| GET | `/api/v1/backtester/sessions` | List backtest sessions |
| POST | `/api/v1/positions/` | Create a position record |
| GET | `/api/v1/positions/` | List positions |
| GET | `/api/v1/positions/{position_id}` | Get one position |
| DELETE | `/api/v1/positions/{position_id}` | Delete a position |
| GET | `/api/v1/positions/{position_id}/pnl` | PnL at given `current_price_a` and `current_price_b` |
| GET | `/api/v1/live/snapshot` | Latest intraday z-score snapshot for the top daily pairs |
| POST | `/api/v1/live/start` | Returns a "started" message; no background loop exists (no-op, see Known limitations) |
| GET | `/api/v1/live/pairs/{asset_a}/{asset_b}/history` | Recent intraday z-score history for one pair |

Request bodies (Pydantic models in `backend/app/api/schemas.py`, `routes_backtester.py`, `routes_positions.py`) are documented in the interactive docs at `/docs`. `POST /api/v1/screener/run` accepts: `assets`, `max_assets` (10-500), `lookback_days` (1-1000), `timeframe` (`1m`, `5m`, `15m`, `1h`, `4h`, `1d`), `min_correlation`, `max_adf_pvalue`, `include_hurst`, `min_volume_usd`.

There is no `/llms.txt` endpoint yet. See Known limitations.

## Authentication and security

- **API key**: set `API_KEY`, then send `X-API-Key: <key>` on every `/api/v1` request. Comparison is constant-time (`hmac.compare_digest`).
- **Cron**: `GET` or `POST /api/v1/screener/cron/run` accepts `Authorization: Bearer <CRON_SECRET>` or the API key. If neither is set, the route is open.
- **Fail-closed startup**: `REQUIRE_AUTH=true` makes the app refuse to start when `API_KEY` is empty.
- **Rate limits**: in-memory, per client IP, per process. Expensive routes (`run`, `run-live`, cron) allow 6 calls per minute. Other `/api/v1` routes allow 240 per minute. Limits reset on restart and are not shared between processes.
- **CORS**: only the origins in `CORS_ORIGINS`. Credentials are disabled.
- **Errors**: most 500 responses return a generic message; details go to the server log.
- Read [`docs/SECURITY.md`](docs/SECURITY.md) for the threat model and checks.

## Database and migrations

- The default database is SQLite at `backend/data/stat_arb.db`. The directory is created on demand. It is git-ignored, but a copy of it was committed in earlier history (see `docs/STATE.md`).
- `init_db()` runs at startup and creates tables with SQLAlchemy `create_all`. An additive `_ensure_columns` step adds missing columns to existing tables. It never drops or renames anything.
- **There are no migrations.** Alembic is listed in `requirements.txt` but no migration directory or configuration exists. Schema changes beyond additive columns need a manual plan. Back up the database file before upgrading.
- For PostgreSQL, set `DATABASE_URL=postgresql://user:pass@host:5432/db`. The same additive rules apply.

## Tests and checks

Run these from the repository root. CI runs the same checks (see `.github/workflows/ci.yml`).

| Check | Command | Expected result |
|---|---|---|
| Backend tests | `cd backend && python -m pytest -q` | 128 passed (verified 2026-11-09) |
| Frontend types | `cd frontend && npx tsc --noEmit` | No output, exit 0 (verified) |
| Frontend build | `cd frontend && npm run build` | `tsc` then `vite build` succeed (verified) |
| Backend lint | `cd backend && python -m ruff check app tests` | All checks passed |
| Backend types | `cd backend && python -m mypy app` | Success, no issues (67 files) |

## Docker

```bash
# Full stack: redis, postgres, data layer, backend, frontend
cp .env.example .env          # then set REDIS_PASSWORD, POSTGRES_PASSWORD and API_KEY
docker compose up -d --build
```

- Frontend http://localhost:3100, backend http://localhost:8000, data layer http://localhost:8001.
- `REDIS_PASSWORD`, `POSTGRES_PASSWORD` and `API_KEY` are required. Compose stops with an error when one is missing.
- All published ports are bound to `127.0.0.1`. Put a TLS reverse proxy in front before exposing anything.
- Data persists in named volumes (`app-redis`, `app-postgres`, `app-backend-data`).
- The frontend nginx image adds `X-API-Key` to every proxied `/api/` request with the value of `API_KEY`. Anyone who can reach the frontend port can use the API. Keep the frontend bound to localhost or behind authentication.

`docker-compose.datalayer.yml` runs only the data layer with its own Redis and PostgreSQL. It hard-codes the PostgreSQL password `datalayer` and publishes ports 6379, 5432 and 8001 on all interfaces. Change both before any use outside a laptop.

`docker compose config` validates both files. The images were not built in the verification of this README.

## Deployment

The repository contains configuration for several hosts. None of them has been verified as deployed in this repository. Treat each as a starting point.

| File | Target | Status |
|---|---|---|
| `Dockerfile` | Docker, Railway (`railway.json` uses the Dockerfile builder) | Compose validated; image build not run here |
| `Procfile`, `nixpacks.toml` | Heroku-style process, Nixpacks | Present; not run here |
| `railway.json`, `railway.datalayer.json` | Railway (backend, data layer as a worker) | Present; not run here |
| `vercel.json`, `backend/serverless_entry.py`, `pyproject.toml` `[tool.vercel]` | Vercel Python runtime with a daily cron on `/api/v1/screener/cron/run` | Present; no long-lived background process exists on this host, so the cron route is the screening trigger |
| `frontend/vercel.json`, `frontend/nixpacks.toml`, `frontend/railway.json` | Frontend static hosting | Present; the frontend has no server-side API key, so `VITE_API_URL` pointing at a protected API will return 401 |
| `DEPLOYMENT_NO_DOCKER.md`, `RAILWAY_DEPLOYMENT.md`, `RAILWAY_DATALAYER.md`, `docs/RUNBOOK.md` | Operating notes | See `docs/RUNBOOK.md` for the current procedure |

Production checklist: set `API_KEY` and `REQUIRE_AUTH=true`, set `CORS_ORIGINS` to your frontend origin, use PostgreSQL for `DATABASE_URL`, use a TLS proxy, and do not publish the data layer ports.

## Documentation

- [`docs/RULES.md`](docs/RULES.md): every rule and formula (cointegration, half-life, Hurst, net edge, composite score, FDR, clustering, Kalman, backtest and metrics).
- [`docs/QA.md`](docs/QA.md): QA scope and results.
- [`docs/SECURITY.md`](docs/SECURITY.md): security review notes and checks. [`SECURITY.md`](SECURITY.md): how to report a vulnerability.
- [`docs/RUNBOOK.md`](docs/RUNBOOK.md): operating procedures.
- `/docs` on a running backend: interactive OpenAPI documentation.

## Known limitations

**Status.** The independent review ([`docs/REVIEW.md`](docs/REVIEW.md)) found no P0 and ten P1 issues; all ten are fixed with tests, along with most P2 items. Open items are tracked in [`docs/REVIEW.md`](docs/REVIEW.md), [`docs/QA.md`](docs/QA.md) and [`docs/SECURITY.md`](docs/SECURITY.md). This is a research tool, not a hardened production service.

Other known gaps:

- **Alerts are in-app only.** `alerts` stores thresholds. There is no Telegram, email or webhook delivery.
- **Live intraday monitor is on demand.** It has no background loop. `POST /api/v1/live/start` is a no-op that returns success. A snapshot is recomputed when someone asks for one.
- **Live screener loop is not started.** `LiveScreener` contains a 30-minute background loop, but nothing calls its `start()` method. Screening runs only when requested (`/run`, `/run-live`), when the cold-start path triggers in `/status`, or through the cron route.
- **`DATA_LAYER_URL` is unused.** It is defined in the settings and described in `.env.example` as the source for the live monitor, but no code path reads it. The monitor fetches candles from Binance through ccxt.
- **`REDIS_URL` is unused by the screener API.** Only the data layer uses Redis.
- **Data layer needs Redis and PostgreSQL.** It fails at startup without Redis (verified: connection refused on `localhost:6379`). Its default `DATABASE_URL` is SQLite, which asyncpg cannot use, so set a `postgresql://` URL.
- **Data layer list variables need JSON.** `DATALAYER_SYMBOLS=BTC/USDT,ETH/USDT` fails with a `SettingsError` (verified). Use `DATALAYER_SYMBOLS=["BTC/USDT","ETH/USDT"]`. The compose comment that shows comma-separated values is wrong.
- **FDR and clustering are not reachable through the API.** `use_fdr` and `use_clustering` exist in `ScreeningConfig` (default off) but `POST /api/v1/screener/run` does not expose them, nor the half-life bounds or the cost model. Those options are reachable only from code.
- **No `/llms.txt`.** The API has no `/llms.txt` route (returns 404), although the project API rules require one.
- **Duplicate OpenAPI operation id.** `GET` and `POST /api/v1/screener/cron/run` share one function, and FastAPI warns about the duplicate id at schema generation. The API works.
- **No migrations.** See Database and migrations.
- **Rate limits are per process and in memory.** Multiple workers or restarts reset them.
- **`backend/run.py` is a dev entry point** (127.0.0.1, `reload=True`). With `API_KEY` unset the API is open to local processes. Set `API_KEY` and `REQUIRE_AUTH=true` for anything shared.
- **Vercel and Railway deployments are not verified** in this repository (see Deployment).
- **Screening results are in memory.** The live screener keeps the current results in process memory and restores the latest session from the database on start.
- **ADF score uses a fixed 0.1 scale.** `adf_score = 1 - p / 0.1` ignores `max_adf_pvalue` (see `docs/RULES.md` section 7).

## License

[MIT](LICENSE), copyright 2026 Keril. To report a vulnerability see [SECURITY.md](SECURITY.md).

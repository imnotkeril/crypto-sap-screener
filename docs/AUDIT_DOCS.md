# Audit: docs (README.md, docs/RULES.md, docs/STATE.md, docs/plan.md, docs/REVIEW.md, docs/SECURITY.md, docs/QA.md, docs/RUNBOOK.md, docs/RELEASE_CHECKLIST.md)
mode: shadow
author-model: sonnet · auditor-model: opus

## Verdict
FIX
Три пункта exit check process/docs.md не выполнены (CHANGELOG, /llms.txt, протокол прогона команд), README обещает срабатывание алертов, которого в режиме по умолчанию нет; всё исправимо по документам.

## Checklist
| # | Item | Result | Evidence |
|---|---|---|---|
| 1 | Every documented command was run; results pasted (list of command -> ok) | FAIL | README.md:281 "The expected results were observed on 2026-10-25." покрывает только 3 проверки; для Quickstart (pip install, npm install, npm run dev, uvicorn, install:all, data_layer.main) нет списка command -> ok; README.md:306 "The images were not built in the verification of this README." |
| 2 | `/llms.txt` endpoint count equals the real route count (both numbers shown) or "no API" | FAIL | README.md:260 "There is no `/llms.txt` endpoint yet." API есть: app.openapi() = 37 операций / 31 путь (совпадает с README.md:216), /llms.txt отсутствует |
| 3 | Env var names in README == names in `.env.example` (diff empty) | PASS | все 25 имён из .env.example есть в таблице README.md:121-150; лишние имена помечены (VITE_BACKEND_URL, data layer), кроме PORT (см. N-02) |
| 4 | CHANGELOG has an entry for the release version with date, no commit dump | FAIL | CHANGELOG.md и docs/CHANGELOG.md отсутствуют (ls); docs/RELEASE_CHECKLIST.md:64 "version/CHANGELOG (no CHANGELOG found)" |
| 5 | No aspirational features described that do not exist | FAIL | README.md:11 "in-app when a pair's z-score crosses a threshold you set" - см. A-01 |

Проверено и совпало с кодом (без находок): структура дерева README vs ls; дефолты env vs backend/app/config.py и data_layer/core/config.py; 37 операций API vs app.openapi(); `python -m pytest -q` -> 88 passed, 5 xfailed; `npx tsc --noEmit` -> exit 0; `python -m mypy app` -> 102 errors in 17 files (mypy 1.20.2); CSV-списки DATALAYER_SYMBOLS -> SettingsError (воспроизведено); /live/start no-op (intraday_monitor.py:69-71); LiveScreener.start() нигде не вызывается; rate limits 6/240 (security.py:65-66); compose 127.0.0.1 и volumes; формулы RULES.md §1-6, §8, §9, §11, §13, §14 vs код; STATE/plan vs git log (7333b2e, 8a03197 и др. есть).

## Findings
- A-01 | P1 | source: checklist:5 | at: README.md:11 | quote: "in-app when a pair's z-score crosses a threshold you set" | scenario: при БД по умолчанию (SQLite) POST /api/v1/alerts пишет в таблицу alerts (routes_alerts.py:75-91), а /alerts/triggered/check и live_screener проверяют только in-memory AlertManager (routes_alerts.py:219-224), поэтому созданный пользователем алерт никогда не срабатывает (QA BUG-1, strict xfail проходит); README.md:333 тоже утверждает 'records triggers' | fix: в What it does и Known limitations написать, что алерты, созданные через API/UI, сейчас не срабатывают (BUG-1), со ссылкой на docs/QA.md
- A-02 | P2 | source: step:docs | at: docs/RUNBOOK.md:60 | quote: "Alerts are in memory only and are lost on restart." | scenario: алерты хранятся в SQLite (DbAlert, routes_alerts.py:80-90) и переживают рестарт; оператор, поверивший runbook, пересоздаст их после рестарта и получит дубли (BUG-4, дедупа нет); то же в RUNBOOK.md:74 и RELEASE_CHECKLIST.md:48 | fix: 'Alerts are stored in SQLite (table alerts) and survive restarts; triggers are evaluated only in memory (BUG-1)'
- A-03 | P2 | source: step:docs | at: docs/RUNBOOK.md:36 | quote: "If it is down the live monitor falls back to direct ccxt/Binance (rate-limit risk)." | scenario: live monitor никогда не использует data layer (DATA_LAYER_URL нигде не читается, grep по backend/app вне config.py пуст; README.md:336 говорит то же), оператор будет чинить data layer ради монитора, на который он не влияет | fix: 'The live monitor does not use the data layer; it always calls Binance through ccxt'
- A-04 | P2 | source: step:review | at: docs/REVIEW.md:20 | quote: "backend/app/modules/screener/kalman.py:289,316-317,333" | scenario: kalman.py имеет 96 строк (и не больше 97 ни в одном коммите), cointegration.py 221 строку, поэтому ссылки R-03, R-02 (cointegration.py:234-239), R-11 (cointegration.py:166,169), R-18 (cointegration.py:173-175) указывают на несуществующие или чужие строки; исполнитель T13 не найдёт место правки по ссылке | fix: перепроверить file:line для R-02, R-03, R-11, R-18 (например Q/R в kalman.py:63-64, Bonferroni в cointegration.py:100, окно в screener.py:438)
- A-05 | P2 | source: step:docs | at: docs/RULES.md:88 | quote: "output `composite_score` in the range 0-100" | scenario: GET /screener/pairs/{id}/spread возвращает поле composite_score по другой формуле (routes.py:767-771: 0.5*corr + 0.3*adf без clamp + 0.2*(1-abs(H-0.5)*2)), так что в деталях пары пользователь видит другой скор, чем в таблице, а каталог, заявленный как 'every rule and formula', об этом молчит | fix: добавить в §7 второй вариант формулы для spread-эндпоинта (или пометить его как известное расхождение)

## Notes (non-blocking)
- N-01 | opinion | at: docs/QA.md:3 | 'are pinned as strict xfail' относится к 7 багам, но strict xfail только 5 (BUG-1,3,5,6,7); BUG-4 и BUG-8 закреплены обычными тестами. Там же QA.md:28 упоминает 'next build', а фронтенд на Vite.
- N-02 | opinion | at: README.md:119 | заявление 'exactly the names in .env.example and backend/app/config.py' неточно: PORT, VITE_BACKEND_URL, VITE_API_URL, REDIS_PASSWORD, POSTGRES_PASSWORD отсутствуют в config.py, PORT не помечен как отсутствующий в .env.example.
- N-03 | opinion | at: docs/RULES.md:192 | пустая строка разрывает таблицу §14, строки long_asset_a / long_asset_b отрендерятся как обычный текст. Kelly в metrics.py:266 возвращается в процентах с clamp [0,100], в §13 это не сказано.
- N-04 | opinion | at: docs/REVIEW.md:36 | R-19 'no not investment advice disclaimer anywhere' устарел для README (дисклеймер есть в README.md:5), но в UI (frontend/src) дисклеймера по-прежнему нет, хотя router finance/screener требует его видимым в UI.
- N-05 | opinion | at: docs/RUNBOOK.md:50 | рискованное допущение документов: что ручной вызов /api/v1/live/start что-то запускает; на деле это no-op (README.md:334 описывает верно), формулировку RUNBOOK стоит выровнять.

## Disposition
| id | verdict | by | note |
|---|---|---|---|

Read: E:/Main/Dev/coding-brain/process/docs.md, E:/Main/Dev/coding-brain/process/review.md (Exit check), E:/Main/Dev/coding-brain/rules/audit.md, E:/Main/Dev/coding-brain/routers/projects/finance/_family.md (Shared checks, Traps), E:/Main/Dev/coding-brain/routers/projects/finance/screener.md (Done when, Traps), README.md, docs/RULES.md, docs/STATE.md, docs/plan.md, docs/REVIEW.md, docs/SECURITY.md, docs/QA.md, docs/RUNBOOK.md, docs/RELEASE_CHECKLIST.md, backend/app/config.py, backend/app/data_layer/core/config.py, backend/app/main.py, backend/app/api/routes.py, backend/app/api/routes_alerts.py, backend/app/api/routes_live.py, backend/app/api/security.py, backend/app/api/schemas.py, backend/app/modules/screener/{screener,cointegration,kalman,intraday_monitor,live_screener,data_loader}.py, backend/app/modules/alerts/alert_manager.py, backend/app/modules/backtester/{backtester,metrics}.py, backend/app/modules/calculator/position_calculator.py, backend/run.py, frontend/vite.config.ts, frontend/nginx.conf.template, frontend/nixpacks.toml, package.json, frontend/package.json, Dockerfile, docker-compose.yml, .env.example (names only via grep -o)

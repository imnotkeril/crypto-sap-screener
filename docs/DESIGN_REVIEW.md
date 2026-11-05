# Design review (light) - 2026-11-05

Scope: built frontend served by the nginx container (compose project `audit-statarb`, port 28462) against a real scan (561 pairs tested, 3 found). Done by the lead agent in the built-in browser, because the design-reviewer subagent had no Playwright tool. **Partial gate:** no full a11y/keyboard/motion pass, no saved screenshots, no pair-detail/Live monitor/Trends pages inspected.

Verdict: **no P0/P1 found in what was checked; gate only partly run.**

| Check | Result |
|---|---|
| 375 / 768 / 1440 horizontal page overflow | none (`scrollWidth == innerWidth` at all three) |
| Mobile (375) layout | header, KPI cards and tabs stack cleanly; pairs table scrolls inside its card (P2: columns beyond SCORE/PAIR are off-screen, no scroll hint; consider a card list under 640px; `frontend/src/components/PairsTable.tsx`) |
| Tap targets <32px at 375 | 0 found among buttons/links/inputs |
| Empty/loading state | "Initializing screener..." with spinner and "first scan may take a few minutes": clear |
| Disclaimer footer | present, color rgb(107,114,128) on rgb(10,10,13): about 4.0:1, slightly under AA 4.5:1 for 12px text (P2, use gray-400) |
| Landmarks | no `<main>` element (P2) |
| Console | one real bug found and fixed: `/api/v1/alerts` redirected to the container-internal port (`127.0.0.1:8080`) -> ERR_CONNECTION_REFUSED; fixed with `proxy_set_header Host $http_host` in `frontend/nginx.conf.template`; verified Location now points to the proxy origin |
| Slop bans | not systematically checked; dark theme with consistent card system, no gradient text/glass seen on the screens above |

Open: run the full design-reviewer with Playwright (keyboard focus, reduced motion, Live monitor, Trends, pair detail), add a `<main>` landmark, raise footer contrast, mobile card layout for the table.

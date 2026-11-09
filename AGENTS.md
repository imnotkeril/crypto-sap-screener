# AGENTS.md — Statistical Arbitrage Pairs Screener

Instructions for any coding agent (Cursor, Codex, Claude Code).

- Goal: screen Binance USDT pairs for statistical arbitrage (cointegration, half-life, net edge), monitor them intraday, with alerts, positions and a backtester. Research tool: no orders are ever sent.
- Stack: Python 3.11 + FastAPI + SQLAlchemy (SQLite default) + ccxt + statsmodels; React 18 + Vite + TypeScript + Tailwind; optional data layer (Redis + Postgres); Docker.
- Router: `finance/screener` (`CLAUDE.md`).
- Read first: `docs/STATE.md` (progress), `docs/plan.md`, `docs/ARCHITECTURE.md` (root `ARCHITECTURE.md`), `README.md`, `docs/AUDIT_2026-10-24.md`.
- Shared conventions: `E:/Main/Dev/coding-brain/rules/` (only the files relevant to your task) and `E:/Main/Dev/coding-brain/known-traps.md`.
- Work one task from `docs/plan.md` at a time; verify (backend `python -m pytest -q`, frontend `npx tsc --noEmit` + `npm run build`), tick it, add a line to `docs/STATE.md`, commit locally.
- Never commit secrets (`.env*`). Never push or deploy without the owner's approval.
- Code, comments and docs in English.

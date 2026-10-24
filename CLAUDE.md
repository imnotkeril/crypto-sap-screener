# Statistical Arbitrage Pairs Screener

Crypto pairs screener (family: finance / screener). FastAPI + SQLAlchemy (SQLite default) backend in `backend/`, React + Vite + TS frontend in `frontend/`, optional market data layer in `backend/app/data_layer/`.

## Commands
- Backend: `cd backend && python -m uvicorn app.main:app --port 8000` (Cyrillic path: use the venv python directly, not `uv run`)
- Frontend: `cd frontend && npm run dev` / `npm run build`
- Tests: `cd backend && python -m pytest -q`; types: `npx tsc --noEmit` (frontend), `mypy app`
- Env: see `.env.example`; never read or commit `.env*`.

## Rules
- Local commits only on `chore/audit`; no push/deploy. No real orders; no live keys.
- Progress: `docs/plan.md` (checkboxes) + `docs/STATE.md`; audit in `docs/AUDIT_2026-10-24.md`.

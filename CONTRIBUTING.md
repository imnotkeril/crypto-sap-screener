# Contributing

Thanks for taking a look. This is a research tool, so small, well-tested changes are the easiest to merge.

## Setup

```bash
# backend
cd backend
pip install -r requirements.txt pytest ruff
python -m pytest -q
python -m ruff check .

# frontend
cd ../frontend
npm ci
npx tsc --noEmit
npm run build
```

Copy `.env.example` to `.env` if you need to change settings. Never commit `.env*` files or exchange keys.

## Pull requests

- Branch from `main`; keep one topic per pull request.
- Add or update a test for every behaviour change (`backend/tests/`).
- `ruff check`, `pytest` and the frontend build must pass; CI runs the same commands.
- Formulas and thresholds live in [`docs/RULES.md`](docs/RULES.md). If you change one, update the doc in the same PR.
- The software must never send orders to an exchange. Changes that add an order path will not be accepted.

## Reporting problems

Use the issue templates. For security problems follow [`SECURITY.md`](SECURITY.md) instead of opening a public issue.

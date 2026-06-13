"""
Entrypoint for Vercel's Python/FastAPI runtime.

The app package uses absolute imports rooted at `backend/` (e.g.
`from app.config import settings`), so `backend/` must be on sys.path
before importing the app. Vercel's FastAPI framework preset imports the
configured entrypoint as a dotted module path from the repo root
(`backend.serverless_entry`), which does not add `backend/` itself to
sys.path - so we do it here.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.main import app  # noqa: E402

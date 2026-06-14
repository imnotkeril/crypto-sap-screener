"""
Entrypoint for the standalone Market Data Layer service.

Run with:
    python -m app.data_layer.main

Runs a FastAPI app (serving layer / query API) with the ingestion pipeline
(WebSocket streaming + backfill) started as a background task. Intended to
run as a persistent process (e.g. a Railway worker service), separate from
the Vercel-hosted screener API.
"""
import logging
import os

import uvicorn

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


def main():
    port = int(os.environ.get("PORT", "8001"))
    uvicorn.run("app.data_layer.serving.api:app", host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()

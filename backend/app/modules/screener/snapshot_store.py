"""Persist the latest screening results as one JSON snapshot in Vercel Blob.

Serverless hosts keep no state between invocations, so a scan finished by the cron
route would be invisible to the next instance. When ``BLOB_READ_WRITE_TOKEN`` is set
(Vercel injects it once a Blob store is connected to the project) the latest results
are written to ``sap/snapshot.json`` and read back on cold start. Without the token
every function is a no-op.
"""
import json
import logging
import os
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

PATHNAME = "sap/snapshot.json"
BLOB_API_URL = os.getenv("VERCEL_BLOB_API_URL", "https://vercel.com/api/blob")


def _token() -> Optional[str]:
    return os.getenv("BLOB_READ_WRITE_TOKEN") or None


def enabled() -> bool:
    return _token() is not None


def _public_url() -> Optional[str]:
    """Public URL of the snapshot. SNAPSHOT_URL overrides; else derived from the token
    (vercel_blob_rw_<storeId>_<secret> -> https://<storeid>.public.blob.vercel-storage.com)."""
    override = os.getenv("SNAPSHOT_URL")
    if override:
        return override
    token = _token()
    if not token:
        return None
    parts = token.split("_")
    if len(parts) < 5:
        return None
    return f"https://{parts[3].lower()}.public.blob.vercel-storage.com/{PATHNAME}"


def save_snapshot(payload: Dict[str, Any]) -> bool:
    """Write the snapshot, replacing the previous one. Never raises."""
    token = _token()
    if not token:
        return False
    try:
        body = json.dumps(payload, default=str).encode("utf-8")
        r = httpx.put(
            BLOB_API_URL,
            params={"pathname": PATHNAME},
            content=body,
            timeout=15,
            headers={
                "authorization": f"Bearer {token}",
                "x-api-version": "12",
                "x-vercel-blob-access": "public",
                "x-add-random-suffix": "0",
                "x-allow-overwrite": "1",
                "x-content-type": "application/json",
                "x-cache-control-max-age": "60",
            },
        )
        if r.status_code >= 300:
            logger.warning(f"Blob snapshot upload failed: HTTP {r.status_code} {r.text[:200]}")
            return False
        return True
    except Exception as e:
        logger.warning(f"Could not save snapshot to Blob: {e}")
        return False


def load_snapshot() -> Optional[Dict[str, Any]]:
    """Read the latest snapshot, or None when missing or unavailable. Never raises."""
    url = _public_url()
    if not url:
        return None
    try:
        r = httpx.get(url, timeout=10, headers={"cache-control": "no-cache"})
        if r.status_code != 200:
            return None
        data = r.json()
        return data if isinstance(data, dict) else None
    except Exception as e:
        logger.warning(f"Could not load snapshot from Blob: {e}")
        return None

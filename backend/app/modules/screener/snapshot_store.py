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
    if not enabled():
        return False
    try:
        from vercel.blob.sync import put_blob
        body = json.dumps(payload, default=str).encode("utf-8")
        put_blob(
            PATHNAME,
            body,
            access="public",
            content_type="application/json",
            allow_overwrite=True,
            cache_control_max_age=60,
        )
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

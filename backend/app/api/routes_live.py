"""
Routes for the intraday live monitor.

Tracks real-time z-score deviations for the top pairs found by the daily
screener, using the already-fitted (alpha, beta, mean, std) of each pair's
spread.
"""
from fastapi import APIRouter, HTTPException
import logging

from app.modules.screener.intraday_monitor import get_intraday_monitor

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/snapshot")
async def get_live_snapshot():
    """Get the latest intraday z-score snapshot for the top daily pairs."""
    monitor = get_intraday_monitor()
    return monitor.get_snapshot()


@router.post("/start")
async def start_live_monitor():
    """Start the intraday monitor background loop (idempotent)."""
    monitor = get_intraday_monitor()
    monitor.start()
    return {"message": "Intraday monitor started", "is_running": monitor.is_running}


@router.get("/pairs/{asset_a}/{asset_b}/history")
async def get_live_pair_history(asset_a: str, asset_b: str):
    """Get the recent intraday z-score history for a specific pair."""
    monitor = get_intraday_monitor()
    history = monitor.get_history(asset_a.upper(), asset_b.upper())
    if not history:
        raise HTTPException(status_code=404, detail="No live history for this pair yet")
    return {"asset_a": asset_a.upper(), "asset_b": asset_b.upper(), "history": history}

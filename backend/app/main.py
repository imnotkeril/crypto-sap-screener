"""
FastAPI application entry point
Works without database - uses in-memory storage
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from datetime import datetime
from app.config import settings
from app.api.routes import router, cron_router
from app.api.security import auth_dependencies
from app.modules.screener.live_screener import get_live_screener
from app.database import init_db
import logging

logger = logging.getLogger(__name__)

# Live screener will be started manually via API endpoint
# No automatic startup to avoid unnecessary Binance API calls

# Create FastAPI app
app = FastAPI(
    title="Statistical Arbitrage Pairs Screener",
    description="API for screening cryptocurrency pairs for statistical arbitrage (Live mode - no database required)",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key", "Authorization"],
)

# Include routers
app.include_router(router, prefix=f"{settings.API_V1_PREFIX}/screener", tags=["screener"], dependencies=auth_dependencies)

# Cron trigger: own auth (CRON_SECRET bearer or API key)
app.include_router(cron_router, prefix=f"{settings.API_V1_PREFIX}/screener", tags=["screener"])

# Include alerts router
from app.api.routes_alerts import router as alerts_router
app.include_router(alerts_router, prefix=f"{settings.API_V1_PREFIX}/alerts", tags=["alerts"], dependencies=auth_dependencies)

# Include backtester router
from app.api.routes_backtester import router as backtester_router
app.include_router(backtester_router, prefix=f"{settings.API_V1_PREFIX}/backtester", tags=["backtester"], dependencies=auth_dependencies)

# Include positions router
from app.api.routes_positions import router as positions_router
app.include_router(positions_router, prefix=f"{settings.API_V1_PREFIX}/positions", tags=["positions"], dependencies=auth_dependencies)

# Include live intraday monitor router
from app.api.routes_live import router as live_router
app.include_router(live_router, prefix=f"{settings.API_V1_PREFIX}/live", tags=["live"], dependencies=auth_dependencies)


@app.on_event("startup")
async def _startup():
    """Initialize database (SQLite by default)"""
    if settings.REQUIRE_AUTH and not settings.API_KEY:
        raise RuntimeError("REQUIRE_AUTH is set but API_KEY is empty")
    if not settings.API_KEY:
        logger.warning("API_KEY is not set: every /api/v1 route is OPEN. Set API_KEY and REQUIRE_AUTH=true for any public deploy.")
    init_db()
    if settings.SCAN_SCHEDULER_ENABLED:
        get_live_screener().start_scheduler(settings.SCAN_INTERVAL_SECONDS)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Statistical Arbitrage Pairs Screener API",
        "version": "1.0.0",
        "mode": "live (in-memory, no database required)",
        "docs": "/docs"
    }


@app.get("/health")
async def health():
    """Liveness + scan freshness. 503 when the scheduler is on and the last scan is stale."""
    try:
        status = get_live_screener().get_status()
    except Exception as e:
        logger.error(f"health: screener status failed: {e}")
        return JSONResponse(status_code=503, content={"status": "unhealthy", "screener_error": str(e)})
    last = status.get('last_screening_time')
    age = None
    if last:
        age = (datetime.utcnow() - datetime.fromisoformat(last)).total_seconds()
    stale = bool(settings.SCAN_SCHEDULER_ENABLED and age is not None
                 and age > 2 * settings.SCAN_INTERVAL_SECONDS)
    body = {
        "status": "stale" if stale else "healthy",
        "screener_running": status['is_running'],
        "pairs_found": status['total_pairs_found'],
        "last_screening_time": last,
        "last_scan_age_seconds": age,
    }
    return JSONResponse(status_code=503 if stale else 200, content=body)

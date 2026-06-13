"""
FastAPI application entry point
Works without database - uses in-memory storage
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.api.routes import router
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
    allow_origins=["*"],  # Allow all origins for Railway deployment (configure specific domains in production)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Include routers
app.include_router(router, prefix=f"{settings.API_V1_PREFIX}/screener", tags=["screener"])

# Include alerts router
from app.api.routes_alerts import router as alerts_router
app.include_router(alerts_router, prefix=f"{settings.API_V1_PREFIX}/alerts", tags=["alerts"])

# Include backtester router
from app.api.routes_backtester import router as backtester_router
app.include_router(backtester_router, prefix=f"{settings.API_V1_PREFIX}/backtester", tags=["backtester"])

# Include positions router
from app.api.routes_positions import router as positions_router
app.include_router(positions_router, prefix=f"{settings.API_V1_PREFIX}/positions", tags=["positions"])

# Include live intraday monitor router
from app.api.routes_live import router as live_router
app.include_router(live_router, prefix=f"{settings.API_V1_PREFIX}/live", tags=["live"])


@app.on_event("startup")
async def _startup():
    """Initialize database (SQLite by default)"""
    init_db()


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
    """Health check endpoint"""
    try:
        live_screener = get_live_screener()
        status = live_screener.get_status()
        return {
            "status": "healthy",
            "screener_running": status['is_running'],
            "pairs_found": status['total_pairs_found']
        }
    except Exception as e:
        return {
            "status": "healthy",
            "screener_error": str(e)
        }

"""
Configuration settings for the application
"""
from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import Optional

class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Database
    # Default to SQLite for a single-file persistence experience.
    # Override via .env / env var DATABASE_URL when needed (e.g., PostgreSQL on a server).
    DATABASE_URL: str = "sqlite:///./data/stat_arb.db"

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def _strip_database_url(cls, v: str) -> str:
        """Strip stray whitespace/newlines (e.g. from copy-pasting into env vars)."""
        if isinstance(v, str):
            return v.strip()
        return v
    
    # Redis (optional)
    REDIS_URL: Optional[str] = "redis://localhost:6379"

    # Market Data Layer (optional) - if set, the live intraday monitor reads
    # ticker prices from this service's HTTP API (real-time via WebSocket)
    # instead of querying Binance directly via ccxt.
    DATA_LAYER_URL: Optional[str] = None
    
    # Binance API
    BINANCE_API_KEY: Optional[str] = None
    BINANCE_API_SECRET: Optional[str] = None
    
    # Screener defaults
    SCREENER_MIN_CORRELATION: float = 0.80
    SCREENER_MAX_ADF_PVALUE: float = 0.10
    SCREENER_LOOKBACK_DAYS: int = 365  # 365 days for crypto (24/7 trading)
    SCREENER_MIN_VOLUME_USD: float = 1_000_000  # 1M USD minimum volume
    SCREENER_MAX_ASSETS: int = 100  # Limit to top 100 assets by volume

    # Intraday live monitor
    INTRADAY_MONITOR_INTERVAL: int = 15  # seconds between live price polls
    INTRADAY_TOP_PAIRS: int = 20  # number of top daily pairs to track live
    INTRADAY_ZSCORE_ALERT_THRESHOLD: float = 2.5  # |z| considered an unusual intraday deviation

    # Intraday Kalman dynamic hedge ratio. The live monitor re-fits beta/alpha
    # online on intraday candles instead of reusing the stale daily fit.
    INTRADAY_KALMAN_TIMEFRAME: str = '5m'  # candle timeframe for the live re-fit
    INTRADAY_KALMAN_LOOKBACK_DAYS: int = 3  # history fed to the filter
    INTRADAY_KALMAN_DELTA: float = 1e-4  # state transition cov (beta agility)
    INTRADAY_KALMAN_R: float = 1e-3  # observation noise variance

    # Security
    API_KEY: Optional[str] = None  # when set, all /api/v1 routes need header X-API-Key
    CRON_SECRET: Optional[str] = None  # Bearer secret for /screener/cron/run
    REQUIRE_AUTH: bool = False  # refuse to start without API_KEY (production)
    CORS_ORIGINS: str = 'http://localhost:5173,http://127.0.0.1:5173,http://localhost:3100'

    AUTO_SCREEN_ON_COLD_START: bool = True  # GET /status starts a scan if none ever ran

    # API
    API_V1_PREFIX: str = "/api/v1"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

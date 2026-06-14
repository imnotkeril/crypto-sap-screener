"""
Configuration settings for the application
"""
from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import Optional
import os

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

    # API
    API_V1_PREFIX: str = "/api/v1"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

"""
Shared data models for modules
"""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class PairInfo(BaseModel):
    """Basic pair information"""
    asset_a: str
    asset_b: str
    correlation: float
    beta: float
    spread_std: float


class ScreeningConfig(BaseModel):
    """Configuration for screening"""
    assets: Optional[list[str]] = None  # None = use top assets by volume
    max_assets: Optional[int] = 100  # Limit number of assets to screen (top N by volume)
    lookback_days: int = 365  # 365 days for crypto (24/7 trading)
    timeframe: str = '1d'  # candle timeframe: 1m, 5m, 15m, 1h, 4h, 1d
    min_correlation: float = 0.80
    max_adf_pvalue: float = 0.10
    include_hurst: bool = False
    min_volume_usd: float = 1_000_000  # 1M USD minimum volume


"""
Pydantic schemas for API requests and responses
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime

VALID_TIMEFRAMES = {'1m', '5m', '15m', '1h', '4h', '1d'}


class ScreeningConfigRequest(BaseModel):
    """Request model for screening configuration"""
    assets: Optional[List[str]] = None
    max_assets: Optional[int] = Field(default=100, ge=10, le=500, description="Maximum number of assets to screen (top N by volume)")
    lookback_days: int = Field(default=365, ge=1, le=1000)
    timeframe: str = Field(default='1d', description="Candle timeframe: 1m, 5m, 15m, 1h, 4h, or 1d")
    min_correlation: float = Field(default=0.80, ge=0.0, le=1.0)
    max_adf_pvalue: float = Field(default=0.10, ge=0.0, le=1.0)
    include_hurst: bool = False
    min_volume_usd: float = Field(default=1_000_000, ge=0, description="Minimum daily volume in USD")

    @field_validator('timeframe')
    @classmethod
    def validate_timeframe(cls, v: str) -> str:
        if v not in VALID_TIMEFRAMES:
            raise ValueError(f"timeframe must be one of {sorted(VALID_TIMEFRAMES)}")
        return v


class PairResult(BaseModel):
    """Single pair screening result"""
    id: int
    asset_a: str
    asset_b: str
    correlation: float
    adf_pvalue: float
    adf_statistic: float
    beta: float
    spread_std: float
    hurst_exponent: Optional[float] = None
    screening_date: datetime
    lookback_days: int
    timeframe: Optional[str] = None
    mean_spread: Optional[float] = None
    min_correlation_window: Optional[float] = None
    max_correlation_window: Optional[float] = None
    composite_score: Optional[float] = None
    current_zscore: Optional[float] = None
    
    model_config = {"from_attributes": True}


class ScreeningSessionResponse(BaseModel):
    """Screening session information"""
    id: int
    started_at: datetime
    completed_at: Optional[datetime]
    total_pairs_tested: int
    pairs_found: int
    status: str


class ScreeningStatusResponse(BaseModel):
    """Current screening status"""
    is_running: bool
    last_session: Optional[ScreeningSessionResponse] = None
    total_pairs_in_db: int
    last_error: Optional[str] = None


class ScreeningResultsResponse(BaseModel):
    """Response with screening results"""
    results: List[PairResult]
    total: int
    session_id: Optional[int] = None


class StatisticsResponse(BaseModel):
    """Statistics about screened pairs"""
    total_pairs: int
    avg_correlation: float
    avg_adf_pvalue: float
    pairs_with_hurst: int
    avg_hurst: Optional[float] = None


class PositionCalculationRequest(BaseModel):
    """Request for position calculation"""
    pair_id: int
    capital: float = Field(gt=0, description="Total capital in USD")
    strategy: str = Field(default="dollar_neutral", description="Position strategy: dollar_neutral, equal_dollar, long_asset_a, long_asset_b")


class AssetPosition(BaseModel):
    """Position details for a single asset"""
    side: str  # "long" or "short"
    quantity: float
    dollar_amount: float
    price: float


class PositionCalculationResponse(BaseModel):
    """Response with calculated position sizes"""
    asset_a: AssetPosition
    asset_b: AssetPosition
    total_capital: float
    strategy: str
    beta: float
    zscore: float
    net_exposure: float

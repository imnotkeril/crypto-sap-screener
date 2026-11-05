"""
Shared data models for modules
"""
from pydantic import BaseModel
from typing import Optional


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

    # Mean-reversion half-life filter (in bars of the chosen timeframe).
    # Pairs reverting faster than min (noise/unstable) or slower than max
    # (too few trades) are rejected when the bound is set. None = no bound.
    min_half_life: Optional[float] = 1.0
    max_half_life: Optional[float] = None
    # Apply Benjamini-Hochberg FDR correction across all candidate p-values to
    # control false discoveries from testing thousands of pairs. alpha =
    # max_adf_pvalue. Strict: with hundreds of candidates it often returns
    # nothing, so it is opt-in. When False the raw per-pair p-value threshold
    # is used (q-values are still attached as adf_pvalue_fdr).
    use_fdr: bool = False

    # Pre-cluster the universe (by return correlation) and only form pairs within
    # a cluster, instead of testing all N*(N-1)/2 combinations. Cuts the number
    # of statistical tests (and false discoveries) and focuses on economically
    # related assets. cluster_distance is the 1-correlation linkage cutoff
    # (0.5 ~ groups assets whose returns correlate above ~0.5).
    use_clustering: bool = False
    cluster_distance: float = 0.5

    # Trading cost model (per-run overridable; defaults mirror app.config). Used
    # to score pairs by NET edge after fees + funding, not just statistical fit.
    taker_fee_bps: float = 5.0  # per fill (Binance USDT-M taker ~0.05%)
    slippage_bps: float = 2.0  # per fill
    funding_bps_per_8h: float = 1.0  # avg |funding| ~0.01%/8h
    entry_zscore: float = 2.0  # z assumed for the entry/exit edge calc


"""
Main screener module that coordinates pair screening
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Dict
from sqlalchemy.orm import Session
from datetime import datetime
import pandas as pd
import logging

from app.modules.screener.data_loader import DataLoader, bars_for_lookback
from app.modules.screener.cointegration import CointegrationTester
from app.modules.screener.correlation import CorrelationAnalyzer
from app.modules.screener.hurst import HurstCalculator
from app.modules.shared.models import ScreeningConfig, PairInfo

logger = logging.getLogger(__name__)


class PairsScreener:
    """Main screener for finding cointegrated pairs"""
    
    def __init__(self, db: Optional[Session] = None):
        self.db = db
        self.data_loader = DataLoader()
        self.cointegration_tester = CointegrationTester()
        self.correlation_analyzer = CorrelationAnalyzer()
        self.hurst_calculator = HurstCalculator()
    
    def screen_pairs(
        self,
        config: ScreeningConfig,
        session_id: Optional[int] = None,
        return_stats: bool = False,
    ):
        """
        Screen pairs for statistical arbitrage opportunities
        
        Args:
            config: Screening configuration
            session_id: Optional session ID for tracking
            
        Returns:
            If return_stats is False: List of screening results
            If return_stats is True: Dict with keys: results, stats
        """
        # Step 1: Get assets to screen (fast - just get list from Binance)
        if config.assets:
            assets = config.assets
        else:
            # Get top Binance USDT perpetual futures by volume
            # Use max_assets limit if specified, otherwise get all assets passing volume filter
            # We'll filter by data availability in the next step
            limit = config.max_assets if config.max_assets else None
            assets = self.data_loader.get_top_assets(
                limit=limit,
                min_volume_usd=config.min_volume_usd
            )

        logger.info(f"Step 1: Found {len(assets)} assets from Binance (after volume filter, max_assets={config.max_assets or 'unlimited'})")
        
        # Step 2: Check data availability for each asset BEFORE forming pairs
        # This is the optimization: filter out assets with insufficient data early
        logger.info(f"Step 2: Checking data availability for {len(assets)} assets (requested: {config.lookback_days} days @ {config.timeframe})")
        min_required_bars = int(bars_for_lookback(config.lookback_days, config.timeframe) * 0.8)  # At least 80% of requested bars

        valid_assets = []
        preload_workers = min(4, len(assets))
        with ThreadPoolExecutor(max_workers=preload_workers) as preload_executor:
            preload_futures = {
                asset: preload_executor.submit(
                    self.data_loader.get_price_series,
                    asset,
                    config.lookback_days,
                    self.db,
                    config.timeframe
                )
                for asset in assets
            }

            # Check each asset's data availability
            for asset, future in preload_futures.items():
                try:
                    price_series = future.result(timeout=60)
                    bars_available = len(price_series)

                    if bars_available >= min_required_bars:
                        valid_assets.append(asset)
                        if bars_available < bars_for_lookback(config.lookback_days, config.timeframe):
                            logger.debug(f"{asset}: {bars_available} bars available (requested {config.lookback_days} days @ {config.timeframe}, using {bars_available})")
                    else:
                        logger.debug(f"{asset}: Only {bars_available} bars available (need at least {min_required_bars}), removing from screening")
                except Exception as e:
                    logger.warning(f"{asset}: Failed to load data - {e}, removing from screening")
                    continue
        
        logger.info(f"Step 3: {len(valid_assets)} assets have sufficient data, {len(assets) - len(valid_assets)} removed")
        
        if len(valid_assets) < 2:
            logger.error("Need at least 2 assets with sufficient data to form pairs")
            return []
        
        # Step 4: Generate pairs only from valid assets
        pairs = []
        for i, asset_a in enumerate(valid_assets):
            for asset_b in valid_assets[i+1:]:
                pairs.append((asset_a, asset_b))
        
        logger.info(f"Step 4: Generated {len(pairs)} pairs from {len(valid_assets)} valid assets")
        
        # Test pairs (with optimized parallel processing)
        results = []
        # Reduced workers to avoid overwhelming the cache and API
        # Since data is pre-loaded, fewer workers should be sufficient
        max_workers = min(4, len(pairs))  # Reduced from 6 to 4 to avoid cache conflicts
        
        logger.info(f"Testing {len(pairs)} pairs with {max_workers} workers")
        processed = 0
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(
                    self._test_pair,
                    asset_a,
                    asset_b,
                    config
                )
                for asset_a, asset_b in pairs
            ]
            
            for future in futures:
                try:
                    # Reduced timeout since data is cached (30 seconds should be enough)
                    result = future.result(timeout=30)
                    if result:
                        results.append(result)
                    processed += 1
                    if processed % 50 == 0:
                        logger.info(f"Processed {processed}/{len(pairs)} pairs, found {len(results)} valid pairs so far")
                except Exception as e:
                    processed += 1
                    if processed % 100 == 0:
                        logger.debug(f"Processed {processed}/{len(pairs)} pairs")
                    continue
        
        logger.info(f"Completed testing {len(pairs)} pairs, found {len(results)} valid pairs")
        
        # Filter and rank results
        filtered_results = [
            r for r in results
            if r['correlation'] >= config.min_correlation
            and r['adf_pvalue'] <= config.max_adf_pvalue
        ]
        
        # Sort by combined score (correlation * (1 - adf_pvalue))
        filtered_results.sort(
            key=lambda x: x['correlation'] * (1 - x['adf_pvalue']),
            reverse=True
        )
        
        # Add metadata to results
        for idx, result in enumerate(filtered_results):
            result['id'] = result.get('id', idx + 1)  # Add ID if not present
            result['screening_date'] = datetime.utcnow()
            result['lookback_days'] = config.lookback_days
            result['timeframe'] = config.timeframe
            result['status'] = 'active'
            if session_id:
                result['session_id'] = session_id
        
        # Optionally save to database if available
        if self.db is not None:
            try:
                from app.database import PairsScreeningResult
                for result in filtered_results:
                    db_result = PairsScreeningResult(
                        session_id=session_id,
                        asset_a=result['asset_a'],
                        asset_b=result['asset_b'],
                        correlation=result['correlation'],
                        adf_pvalue=result['adf_pvalue'],
                        adf_statistic=result['adf_statistic'],
                        beta=result['beta'],
                        alpha=result.get('alpha'),
                        spread_std=result['spread_std'],
                        hurst_exponent=result.get('hurst_exponent'),
                        lookback_days=config.lookback_days,
                        mean_spread=result.get('mean_spread'),
                        min_correlation_window=result.get('min_correlation'),
                        max_correlation_window=result.get('max_correlation'),
                        composite_score=result.get('composite_score'),
                        current_zscore=result.get('current_zscore'),
                        status='active'
                    )
                    self.db.add(db_result)
                self.db.commit()
            except Exception as e:
                logger.warning(f"Could not save to database: {e}")
        
        logger.info(f"Found {len(filtered_results)} valid pairs")
        
        if not return_stats:
            return filtered_results

        stats = {
            "assets_count": len(assets),
            "valid_assets_count": len(valid_assets),
            "pairs_generated": len(pairs),
            "pairs_processed": processed,
            "pairs_found": len(filtered_results),
            "started_at": datetime.utcnow().isoformat(),
            "config": {
                "lookback_days": config.lookback_days,
                "timeframe": config.timeframe,
                "min_correlation": config.min_correlation,
                "max_adf_pvalue": config.max_adf_pvalue,
                "include_hurst": config.include_hurst,
                "min_volume_usd": config.min_volume_usd,
                "max_assets": config.max_assets,
            },
        }

        return {"results": filtered_results, "stats": stats}
    
    def _test_pair(
        self,
        asset_a: str,
        asset_b: str,
        config: ScreeningConfig
    ) -> Optional[Dict]:
        """
        Test a single pair for cointegration and correlation
        
        Args:
            asset_a: First asset symbol
            asset_b: Second asset symbol
            config: Screening configuration
            
        Returns:
            Dictionary with test results or None if pair is invalid
        """
        try:
            # Load price data (uses cache if available)
            price_a = self.data_loader.get_price_series(
                asset_a,
                days=config.lookback_days,
                db=self.db,
                timeframe=config.timeframe
            )
            price_b = self.data_loader.get_price_series(
                asset_b,
                days=config.lookback_days,
                db=self.db,
                timeframe=config.timeframe
            )

            # Check data availability (should already be validated, but double-check)
            min_required_bars = int(bars_for_lookback(config.lookback_days, config.timeframe) * 0.8)
            if len(price_a) < min_required_bars or len(price_b) < min_required_bars:
                # This shouldn't happen if filtering worked correctly, but log it
                logger.warning(f"Pair {asset_a}-{asset_b} has insufficient data: {len(price_a)} and {len(price_b)} bars (need {min_required_bars})")
                return None
            
            # OPTIMIZATION: Fast correlation check FIRST (before slow cointegration test)
            # This filters out bad pairs quickly
            corr, min_corr, max_corr = self.correlation_analyzer.calculate_correlation(
                price_a, price_b
            )
            
            # Quick pre-filter: reject pairs with very low correlation (not too strict)
            # Use 90% of threshold to avoid rejecting good pairs, but filter out bad ones
            quick_filter_threshold = max(0.7, config.min_correlation * 0.9)
            if corr < quick_filter_threshold:
                return None  # Fast rejection before expensive cointegration test
            
            # Now do the expensive cointegration test (only for pairs with good correlation)
            is_cointegrated, beta, adf_stat, adf_pvalue, spread_std = \
                self.cointegration_tester.engle_granger_test(price_a, price_b)
            
            if not is_cointegrated:
                return None
            
            # Final strict correlation check
            if corr < config.min_correlation:
                return None
            
            # Get alpha from regression for accurate spread calculation
            # Re-run regression to get alpha
            aligned = pd.DataFrame({'a': price_a, 'b': price_b}).dropna()
            if len(aligned) < 50:
                return None
            
            from statsmodels.regression.linear_model import OLS
            import numpy as np
            X = aligned['b'].values.reshape(-1, 1)
            y = aligned['a'].values
            X_with_const = np.column_stack([np.ones(len(X)), X])
            model = OLS(y, X_with_const).fit()
            alpha = model.params[0]
            
            # Calculate spread for additional metrics
            spread = self.cointegration_tester.calculate_spread(price_a, price_b, beta, alpha)
            mean_spread = spread.mean()
            
            # Calculate current z-score
            zscore = self.cointegration_tester.calculate_zscore(spread)
            current_zscore = float(zscore.iloc[-1]) if len(zscore) > 0 else 0.0
            
            result = {
                'asset_a': asset_a,
                'asset_b': asset_b,
                'correlation': corr,
                'min_correlation': min_corr,
                'max_correlation': max_corr,
                'adf_pvalue': adf_pvalue,
                'adf_statistic': adf_stat,
                'alpha': float(alpha),
                'beta': beta,
                'spread_std': spread_std,
                'mean_spread': mean_spread,
                'current_zscore': current_zscore
            }
            
            # Optional: Calculate Hurst exponent
            if config.include_hurst:
                hurst = self.hurst_calculator.generalized_hurst_exponent(spread)
                result['hurst_exponent'] = hurst
            else:
                result['hurst_exponent'] = None
            
            # Calculate composite score (pair strength indicator)
            # Higher correlation + lower ADF p-value + lower Hurst = better pair
            hurst = result.get('hurst_exponent', 0.5)
            if hurst is None:
                hurst = 0.5
            
            correlation_score = corr  # 0-1
            adf_score = 1.0 - (adf_pvalue / 0.1)  # 0-1 (better if lower p-value)
            adf_score = max(0.0, min(1.0, adf_score))  # Clamp to [0, 1]
            hurst_score = 1.0 - abs(hurst - 0.5) * 2  # 0-1 (better if closer to 0.5)
            hurst_score = max(0.0, min(1.0, hurst_score))  # Clamp to [0, 1]
            
            composite_score = (correlation_score * 0.5 + adf_score * 0.3 + hurst_score * 0.2) * 100
            result['composite_score'] = composite_score
            
            return result
            
        except Exception as e:
            logger.error(f"Error testing pair {asset_a}-{asset_b}: {e}")
            return None


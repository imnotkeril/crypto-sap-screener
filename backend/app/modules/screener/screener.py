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

from app.modules.screener.data_loader import DataLoader, bars_for_lookback, TIMEFRAME_MS
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
        
        # Step 4: Generate pairs from valid assets. Optionally pre-cluster the
        # universe by return correlation and only form within-cluster pairs, so
        # we test far fewer combinations (fewer false discoveries, focus on
        # economically related assets).
        if config.use_clustering and len(valid_assets) > 2:
            pairs = self._clustered_pairs(valid_assets, config)
        else:
            pairs = [
                (asset_a, asset_b)
                for i, asset_a in enumerate(valid_assets)
                for asset_b in valid_assets[i + 1:]
            ]

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
        def _half_life_ok(r) -> bool:
            hl = r.get('half_life')
            if config.min_half_life is not None and (hl is None or hl < config.min_half_life):
                return False
            if config.max_half_life is not None and (hl is None or hl > config.max_half_life):
                return False
            return True

        filtered_results = [
            r for r in results
            if r['correlation'] >= config.min_correlation
            and r['adf_pvalue'] <= config.max_adf_pvalue
            and _half_life_ok(r)
        ]

        # Multiple-testing correction. We test ~N*(N-1)/2 pairs, so a raw
        # p-value threshold yields many false discoveries (e.g. 4950 pairs at
        # p<0.10 => ~495 spurious "cointegrated" pairs from noise alone).
        # Benjamini-Hochberg FDR controls the expected fraction of false
        # positives among the selected pairs.
        if config.use_fdr and len(filtered_results) > 1:
            try:
                from statsmodels.stats.multitest import multipletests
                pvals = [r['adf_pvalue'] for r in filtered_results]
                reject, pvals_corrected, _, _ = multipletests(
                    pvals, alpha=config.max_adf_pvalue, method='fdr_bh'
                )
                kept = []
                for r, rej, pc in zip(filtered_results, reject, pvals_corrected):
                    if rej:
                        r['adf_pvalue_fdr'] = float(pc)
                        kept.append(r)
                logger.info(
                    f"FDR (Benjamini-Hochberg @ alpha={config.max_adf_pvalue}): "
                    f"kept {len(kept)}/{len(filtered_results)} pairs"
                )
                filtered_results = kept
            except Exception as e:
                logger.warning(f"FDR correction failed, using raw p-values: {e}")

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
                        half_life=result.get('half_life'),
                        expected_net_edge_pct=result.get('expected_net_edge_pct'),
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
                "min_half_life": config.min_half_life,
                "max_half_life": config.max_half_life,
                "use_fdr": config.use_fdr,
                "use_clustering": config.use_clustering,
                "cluster_distance": config.cluster_distance,
            },
        }

        return {"results": filtered_results, "stats": stats}
    
    def _clustered_pairs(self, assets: List[str], config: ScreeningConfig):
        """Group assets by return correlation and return only within-cluster pairs.

        Uses average-linkage hierarchical clustering on a (1 - correlation)
        distance, cut at ``config.cluster_distance``. Falls back to all pairs if
        the return matrix can't be built. Series are read from cache (already
        preloaded during the data-availability check).
        """
        import numpy as np
        from scipy.cluster.hierarchy import linkage, fcluster
        from scipy.spatial.distance import squareform

        def _all_pairs(items):
            return [
                (items[i], items[j])
                for i in range(len(items))
                for j in range(i + 1, len(items))
            ]

        try:
            series = {}
            for a in assets:
                s = self.data_loader.get_price_series(
                    a, days=config.lookback_days, db=self.db, timeframe=config.timeframe
                )
                if len(s) > 0:
                    series[a] = s

            df = pd.DataFrame(series).dropna()
            if df.shape[1] < 2 or df.shape[0] < 10:
                logger.warning("Clustering: not enough aligned data, using all pairs")
                return _all_pairs(assets)

            returns = df.pct_change().dropna()
            corr = returns.corr()
            cols = list(corr.columns)

            dist = 1.0 - corr.values
            dist = (dist + dist.T) / 2.0  # enforce symmetry
            np.fill_diagonal(dist, 0.0)
            dist = np.clip(dist, 0.0, 2.0)

            condensed = squareform(dist, checks=False)
            Z = linkage(condensed, method='average')
            labels = fcluster(Z, t=config.cluster_distance, criterion='distance')

            clusters: Dict[int, List[str]] = {}
            for col, lab in zip(cols, labels):
                clusters.setdefault(int(lab), []).append(col)

            pairs = []
            for members in clusters.values():
                pairs.extend(_all_pairs(members))

            all_n = len(cols) * (len(cols) - 1) // 2
            logger.info(
                f"Clustering: {len(cols)} assets -> {len(clusters)} clusters -> "
                f"{len(pairs)} within-cluster pairs (vs {all_n} all-pairs)"
            )
            # Add back any assets dropped from the correlation matrix as their own
            # singletons (no pairs) - they simply won't be tested.
            return pairs if pairs else _all_pairs(assets)
        except Exception as e:
            logger.warning(f"Clustering failed ({e}), falling back to all pairs")
            return _all_pairs(assets)

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

            # Half-life of mean reversion (in bars of this timeframe)
            half_life = self.cointegration_tester.half_life(spread)

            # Current z-score. Prefer a rolling z-score (window = half-life) so
            # the reading reflects only trailing information rather than peeking
            # at the full-sample mean/std. Fall back to the static z-score when
            # there is no usable half-life.
            if half_life is not None and half_life >= 1:
                window = int(min(max(half_life, 5), max(5, len(spread) // 2)))
                rolling_z = self.cointegration_tester.rolling_zscore(spread, window)
                current_zscore = float(rolling_z.iloc[-1]) if len(rolling_z) > 0 else 0.0
            else:
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
                'current_zscore': current_zscore,
                'half_life': half_life,
            }

            # Expected NET edge per round-trip trade, after costs. A pair that is
            # statistically perfect but whose mean-reversion amplitude doesn't
            # clear fees + funding is not tradeable. spread_std is already a % of
            # price A, so the gross move from |z|=entry back to 0 is
            # entry_z * spread_std (%). Costs: 4 taker fills (open+close, 2 legs)
            # plus funding over the holding period (~ half-life).
            entry_z = config.entry_zscore
            gross_edge_pct = entry_z * spread_std
            fee_slip_pct = 4.0 * (config.taker_fee_bps + config.slippage_bps) * 0.01
            bar_hours = TIMEFRAME_MS.get(config.timeframe, TIMEFRAME_MS['1d']) / 3_600_000.0
            if half_life is not None and half_life > 0:
                holding_hours = half_life * bar_hours
                funding_pct = (holding_hours / 8.0) * config.funding_bps_per_8h * 0.01
            else:
                funding_pct = 0.0
            net_edge_pct = gross_edge_pct - fee_slip_pct - funding_pct
            result['expected_net_edge_pct'] = float(net_edge_pct)
            
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

            # Net-edge score: fraction of the gross reversion that survives costs.
            # 0 when the trade doesn't clear fees+funding, 1 when costs are
            # negligible relative to the move.
            if gross_edge_pct > 0:
                net_edge_score = max(0.0, min(1.0, net_edge_pct / gross_edge_pct))
            else:
                net_edge_score = 0.0

            composite_score = (
                correlation_score * 0.4
                + adf_score * 0.25
                + hurst_score * 0.15
                + net_edge_score * 0.2
            ) * 100
            result['composite_score'] = composite_score
            
            return result
            
        except Exception as e:
            logger.error(f"Error testing pair {asset_a}-{asset_b}: {e}")
            return None


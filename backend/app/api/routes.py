"""
FastAPI routes for pairs screener
Uses in-memory live screener for real-time data
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
import io
import pandas as pd

from app.database import get_db
from app.database import SessionLocal, ScreeningSession, PairsScreeningResult
from app.api.schemas import (
    ScreeningConfigRequest,
    PairResult,
    ScreeningStatusResponse,
    ScreeningResultsResponse,
    ScreeningSessionResponse,
    StatisticsResponse,
    PositionCalculationRequest,
    PositionCalculationResponse,
    AssetPosition
)
from app.modules.screener.screener import PairsScreener
from app.modules.screener.live_screener import get_live_screener
from app.modules.shared.models import ScreeningConfig
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# Global variable to track running screening
_screening_in_progress = False


@router.get("/debug/db")
async def debug_db():
    """Temporary diagnostic endpoint to check DB connectivity."""
    import traceback
    from app.config import settings
    from app.database import engine, make_url
    result = {"database_url_set": bool(settings.DATABASE_URL)}
    try:
        u = make_url(settings.DATABASE_URL)
        result["url_drivername"] = u.drivername
        result["url_host"] = u.host
        result["url_port"] = u.port
        result["url_database"] = u.database
        result["url_username"] = u.username
    except Exception as e:
        result["url_parse_error"] = str(e)
    try:
        if engine is None:
            result["engine"] = None
        else:
            from sqlalchemy import text
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            result["connection"] = "ok"
    except Exception as e:
        result["connection_error"] = str(e)
        result["traceback"] = traceback.format_exc()
    return result


@router.get("/sessions")
async def get_screening_sessions(limit: int = 50, db: Session = Depends(get_db)):
    """Get persisted screening sessions (history)."""
    if db is None:
        return {"sessions": [], "total": 0}

    q = db.query(ScreeningSession).order_by(
        ScreeningSession.completed_at.desc().nullslast(),
        ScreeningSession.started_at.desc()
    )
    total = q.count()
    rows = q.limit(limit).all()

    sessions = []
    for s in rows:
        sessions.append({
            "id": s.id,
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "completed_at": s.completed_at.isoformat() if s.completed_at else None,
            "total_pairs_tested": s.total_pairs_tested,
            "pairs_found": s.pairs_found,
            "status": s.status,
            "config": s.config,
        })
    return {"sessions": sessions, "total": total}


@router.get("/pairs/history")
async def get_pair_history_by_symbols(
    asset_a: str,
    asset_b: str,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """Get persisted history for a specific pair across screening sessions."""
    if db is None:
        return {"pair": {"asset_a": asset_a, "asset_b": asset_b}, "history": []}

    # Normalize ordering so A-B and B-A are treated the same.
    a1, b1 = (asset_a, asset_b) if asset_a <= asset_b else (asset_b, asset_a)

    q = db.query(PairsScreeningResult).filter(
        ((PairsScreeningResult.asset_a == a1) & (PairsScreeningResult.asset_b == b1)) |
        ((PairsScreeningResult.asset_a == b1) & (PairsScreeningResult.asset_b == a1))
    ).order_by(PairsScreeningResult.screening_date.desc())

    rows = q.limit(limit).all()
    history = []
    for r in rows:
        history.append({
            "id": r.id,
            "session_id": r.session_id,
            "screening_date": r.screening_date.isoformat() if r.screening_date else None,
            "correlation": r.correlation,
            "adf_pvalue": r.adf_pvalue,
            "adf_statistic": r.adf_statistic,
            "beta": r.beta,
            "spread_std": r.spread_std,
            "hurst_exponent": r.hurst_exponent,
            "mean_spread": r.mean_spread,
            "min_correlation_window": r.min_correlation_window,
            "max_correlation_window": r.max_correlation_window,
            "composite_score": r.composite_score,
            "current_zscore": r.current_zscore,
            "lookback_days": r.lookback_days,
        })

    return {"pair": {"asset_a": a1, "asset_b": b1}, "history": history}


@router.get("/status", response_model=ScreeningStatusResponse)
async def get_screening_status(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Get current screening status from live screener"""
    try:
        live_screener = get_live_screener()
        status = live_screener.get_status()
        last_session = live_screener.get_last_session()

        # Cold start: no screening session has ever run (e.g. first deploy,
        # empty database). Kick off a screening run in the background so the
        # UI doesn't stay stuck on "Initializing screener..." forever.
        if last_session is None and not status['is_running']:
            background_tasks.add_task(live_screener._run_screening)

        last_session_response = None
        if last_session:
            # Parse datetime strings
            started_at = last_session['started_at']
            if isinstance(started_at, str):
                started_at = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
            
            completed_at = last_session.get('completed_at')
            if completed_at and isinstance(completed_at, str):
                completed_at = datetime.fromisoformat(completed_at.replace('Z', '+00:00'))
            
            last_session_response = ScreeningSessionResponse(
                id=last_session['id'],
                started_at=started_at,
                completed_at=completed_at,
                total_pairs_tested=last_session['total_pairs_tested'],
                pairs_found=last_session['pairs_found'],
                status=last_session['status']
            )
        
        return ScreeningStatusResponse(
            is_running=status['is_running'],
            last_session=last_session_response,
            total_pairs_in_db=status['total_pairs_found']
        )
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        return ScreeningStatusResponse(
            is_running=False,
            last_session=None,
            total_pairs_in_db=0
        )


@router.get("/cron/run")
async def cron_run_screening():
    """Synchronous screening run for scheduled triggers (e.g. Vercel Cron).

    Runs to completion within the request so it works without a persistent
    background process.
    """
    try:
        live_screener = get_live_screener()
        live_screener._run_screening()
        return {
            "status": "completed",
            "pairs_found": len(live_screener.get_results()),
            "last_session": live_screener.get_last_session(),
        }
    except Exception as e:
        logger.error(f"Cron screening failed: {e}")
        raise HTTPException(status_code=500, detail=f"Cron screening failed: {str(e)}")


@router.post("/run-live")
async def run_live_screening(background_tasks: BackgroundTasks):
    """Manually trigger live screener to run (fetches fresh data from Binance)"""
    try:
        live_screener = get_live_screener()
        
        if live_screener.is_running:
            raise HTTPException(status_code=400, detail="Screening is already running")
        
        # Run in background
        background_tasks.add_task(live_screener._run_screening)
        
        return {
            "message": "Live screening started",
            "status": "running",
            "note": "Fetching fresh asset list from Binance..."
        }
    except Exception as e:
        logger.error(f"Error starting live screening: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start screening: {str(e)}")


@router.post("/run", response_model=ScreeningSessionResponse)
async def run_screening(
    config: ScreeningConfigRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Start a new screening session (runs in memory)"""
    global _screening_in_progress
    
    if _screening_in_progress:
        raise HTTPException(status_code=400, detail="Screening already in progress")
    
    # Convert to internal config
    screening_config = ScreeningConfig(
        assets=config.assets,
        max_assets=config.max_assets,
        lookback_days=config.lookback_days,
        min_correlation=config.min_correlation,
        max_adf_pvalue=config.max_adf_pvalue,
        include_hurst=config.include_hurst,
        min_volume_usd=config.min_volume_usd
    )
    
    # Create session info
    session_id = int(datetime.utcnow().timestamp())
    session_start = datetime.utcnow()
    
    # Run screening in background
    background_tasks.add_task(
        _run_screening_background,
        session_id,
        screening_config
    )
    
    return ScreeningSessionResponse(
        id=session_id,
        started_at=session_start,
        completed_at=None,
        total_pairs_tested=0,
        pairs_found=0,
        status="running"
    )


def _run_screening_background(session_id: int, config: ScreeningConfig):
    """Background task for running screening"""
    global _screening_in_progress
    
    _screening_in_progress = True
    
    try:
        logger.info(f"Starting background screening with lookback_days={config.lookback_days}")
        # Run screener WITHOUT database - use memory only
        screener = PairsScreener(db=None)
        out = screener.screen_pairs(config, session_id=session_id, return_stats=True)
        results = out.get("results", []) if isinstance(out, dict) else (out or [])
        stats = out.get("stats", {}) if isinstance(out, dict) else {}
        
        # Update live screener with results IMMEDIATELY (memory is primary source for UI)
        live_screener = get_live_screener()
        with live_screener._lock:
            live_screener.current_results = results
            # Update last session info
            live_screener.last_session_info = {
                'id': session_id,
                'started_at': datetime.utcnow().isoformat(),
                'completed_at': datetime.utcnow().isoformat(),
                'total_pairs_tested': int(stats.get("pairs_generated", 0) or 0),
                'pairs_found': len(results),
                'status': 'completed',
                'config': {
                    'lookback_days': config.lookback_days,
                    'min_correlation': config.min_correlation,
                    'max_adf_pvalue': config.max_adf_pvalue,
                    'include_hurst': config.include_hurst
                }
            }
            live_screener.last_screening_time = datetime.utcnow()
        
        logger.info(f"Background screening completed: {len(results)} pairs found and updated in memory")
        
    except Exception as e:
        logger.error(f"Error in background screening: {e}")
        import traceback
        traceback.print_exc()
    finally:
        _screening_in_progress = False


@router.get("/results", response_model=ScreeningResultsResponse)
async def get_screening_results(
    limit: int = 50,
    min_correlation: Optional[float] = None,
    sort_by: str = "correlation",
    min_beta: Optional[float] = None,
    max_beta: Optional[float] = None,
    min_spread_std: Optional[float] = None,
    max_spread_std: Optional[float] = None,
    updated_since: Optional[float] = None,  # Unix timestamp
    session_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get screening results from live screener (in-memory)"""
    try:
        live_screener = get_live_screener()
        results = live_screener.get_results()
        
        # Filter by correlation
        if min_correlation:
            results = [r for r in results if r.get('correlation', 0) >= min_correlation]
        
        # Filter by beta
        if min_beta is not None:
            results = [r for r in results if r.get('beta', 0) >= min_beta]
        if max_beta is not None:
            results = [r for r in results if r.get('beta', 0) <= max_beta]
        
        # Filter by spread_std
        if min_spread_std is not None:
            results = [r for r in results if r.get('spread_std', 0) >= min_spread_std]
        if max_spread_std is not None:
            results = [r for r in results if r.get('spread_std', 0) <= max_spread_std]
        
        # Filter by update time (if screening_date is available)
        if updated_since is not None:
            updated_since_dt = datetime.fromtimestamp(updated_since)
            results = [
                r for r in results
                if r.get('screening_date') and (
                    isinstance(r['screening_date'], datetime) and r['screening_date'] >= updated_since_dt
                    or isinstance(r['screening_date'], str) and datetime.fromisoformat(r['screening_date'].replace('Z', '+00:00')) >= updated_since_dt
                )
            ]
        
        # Sort
        if sort_by == "correlation":
            results.sort(key=lambda x: x.get('correlation', 0), reverse=True)
        elif sort_by == "adf_pvalue":
            results.sort(key=lambda x: x.get('adf_pvalue', 1.0))
        elif sort_by == "beta":
            results.sort(key=lambda x: x.get('beta', 0), reverse=True)
        else:
            # Sort by screening_date
            results.sort(key=lambda x: x.get('screening_date', datetime.min), reverse=True)
        
        # Limit
        total = len(results)
        results = results[:limit]
        
        # Convert to PairResult format
        pair_results = []
        for idx, result in enumerate(results):
            # Generate ID if not present
            pair_id = result.get('id', idx + 1)
            
            # Handle screening_date - can be datetime or string
            screening_date = result.get('screening_date', datetime.utcnow())
            if isinstance(screening_date, str):
                try:
                    screening_date = datetime.fromisoformat(screening_date.replace('Z', '+00:00'))
                except (ValueError, TypeError):
                    screening_date = datetime.utcnow()
            
            pair_result = PairResult(
                id=pair_id,
                asset_a=result['asset_a'],
                asset_b=result['asset_b'],
                correlation=result['correlation'],
                adf_pvalue=result['adf_pvalue'],
                adf_statistic=result['adf_statistic'],
                beta=result['beta'],
                spread_std=result['spread_std'],
                hurst_exponent=result.get('hurst_exponent'),
                screening_date=screening_date,
                lookback_days=result.get('lookback_days', 365),
                mean_spread=result.get('mean_spread'),
                min_correlation_window=result.get('min_correlation'),  # screener uses 'min_correlation' key
                max_correlation_window=result.get('max_correlation'),  # screener uses 'max_correlation' key
                composite_score=result.get('composite_score'),
                current_zscore=result.get('current_zscore')
            )
            pair_results.append(pair_result)
        
        return ScreeningResultsResponse(
            results=pair_results,
            total=total
        )
    except Exception as e:
        logger.error(f"Error getting screening results: {e}")
        import traceback
        traceback.print_exc()
        return ScreeningResultsResponse(results=[], total=0)


@router.get("/pairs/{pair_id}", response_model=PairResult)
async def get_pair_details(pair_id: int, db: Session = Depends(get_db)):
    """Get details for a specific pair from live screener"""
    try:
        live_screener = get_live_screener()
        results = live_screener.get_results()
        
        # Find pair by ID or index
        pair = None
        for idx, result in enumerate(results):
            if result.get('id') == pair_id or (idx + 1) == pair_id:
                pair = result
                break
        
        if not pair and db is not None:
            # Fallback: pair_id can be a persisted DB row id
            row = db.query(PairsScreeningResult).filter(PairsScreeningResult.id == pair_id).first()
            if row:
                return PairResult(
                    id=row.id,
                    asset_a=row.asset_a,
                    asset_b=row.asset_b,
                    correlation=row.correlation,
                    adf_pvalue=row.adf_pvalue,
                    adf_statistic=row.adf_statistic,
                    beta=row.beta,
                    spread_std=row.spread_std,
                    hurst_exponent=row.hurst_exponent,
                    screening_date=row.screening_date,
                    lookback_days=row.lookback_days,
                    mean_spread=row.mean_spread,
                    min_correlation_window=row.min_correlation_window,
                    max_correlation_window=row.max_correlation_window,
                    composite_score=row.composite_score,
                    current_zscore=row.current_zscore,
                )

        if not pair:
            raise HTTPException(status_code=404, detail="Pair not found")
        
        # Handle screening_date - can be datetime or string
        screening_date = pair.get('screening_date', datetime.utcnow())
        if isinstance(screening_date, str):
            try:
                screening_date = datetime.fromisoformat(screening_date.replace('Z', '+00:00'))
            except (ValueError, TypeError):
                screening_date = datetime.utcnow()
        
        return PairResult(
            id=pair_id,
            asset_a=pair['asset_a'],
            asset_b=pair['asset_b'],
            correlation=pair['correlation'],
            adf_pvalue=pair['adf_pvalue'],
            adf_statistic=pair['adf_statistic'],
            beta=pair['beta'],
            spread_std=pair['spread_std'],
            hurst_exponent=pair.get('hurst_exponent'),
            screening_date=screening_date,
            lookback_days=pair.get('lookback_days', 365),
            mean_spread=pair.get('mean_spread'),
            min_correlation_window=pair.get('min_correlation'),  # screener uses 'min_correlation' key
            max_correlation_window=pair.get('max_correlation'),  # screener uses 'max_correlation' key
            composite_score=pair.get('composite_score'),
            current_zscore=pair.get('current_zscore')
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting pair details: {e}")
        raise HTTPException(status_code=503, detail=f"Error: {str(e)}")


@router.get("/stats", response_model=StatisticsResponse)
async def get_statistics(db: Session = Depends(get_db)):
    """Get overall statistics from live screener"""
    try:
        live_screener = get_live_screener()
        results = live_screener.get_results()
        
        if not results:
            return StatisticsResponse(
                total_pairs=0,
                avg_correlation=0.0,
                avg_adf_pvalue=0.0,
                pairs_with_hurst=0,
                avg_hurst=None
            )
        
        total = len(results)
        avg_correlation = sum(r.get('correlation', 0) for r in results) / total
        avg_adf_pvalue = sum(r.get('adf_pvalue', 0) for r in results) / total
        
        pairs_with_hurst = [r for r in results if r.get('hurst_exponent') is not None]
        avg_hurst = None
        if pairs_with_hurst:
            avg_hurst = sum(r['hurst_exponent'] for r in pairs_with_hurst) / len(pairs_with_hurst)
        
        return StatisticsResponse(
            total_pairs=total,
            avg_correlation=avg_correlation,
            avg_adf_pvalue=avg_adf_pvalue,
            pairs_with_hurst=len(pairs_with_hurst),
            avg_hurst=avg_hurst
        )
    except Exception as e:
        logger.error(f"Error getting statistics: {e}")
        return StatisticsResponse(
            total_pairs=0,
            avg_correlation=0.0,
            avg_adf_pvalue=0.0,
            pairs_with_hurst=0,
            avg_hurst=None
        )


@router.get("/pairs/{pair_id}/spread")
async def get_pair_spread_data(pair_id: int):
    """Get spread and z-score data for a specific pair for charting"""
    try:
        live_screener = get_live_screener()
        results = live_screener.get_results()
        
        # Find pair by ID or index
        pair = None
        for idx, result in enumerate(results):
            if result.get('id') == pair_id or (idx + 1) == pair_id:
                pair = result
                break
        
        if not pair:
            raise HTTPException(status_code=404, detail="Pair not found")
        
        # Load price data and calculate spread
        from app.modules.screener.screener import PairsScreener
        from app.modules.screener.data_loader import DataLoader
        from app.modules.shared.models import ScreeningConfig
        from app.config import settings
        
        data_loader = DataLoader()
        lookback_days = pair.get('lookback_days', settings.SCREENER_LOOKBACK_DAYS)
        
        # Load price series - always fetch fresh data to ensure we have the requested period
        # Clear cache for this symbol/days combination to force fresh fetch
        price_a = data_loader.get_price_series(pair['asset_a'], days=lookback_days, db=None)
        price_b = data_loader.get_price_series(pair['asset_b'], days=lookback_days, db=None)
        
        # Verify we have enough data points (at least 80% of requested days)
        min_required_points = int(lookback_days * 0.8)
        if len(price_a) < min_required_points or len(price_b) < min_required_points:
            # If we don't have enough data, try to fetch more
            # This can happen if cache had less data than requested
            data_loader.clear_cache(pair['asset_a'], lookback_days)
            data_loader.clear_cache(pair['asset_b'], lookback_days)
            price_a = data_loader.get_price_series(pair['asset_a'], days=lookback_days, db=None)
            price_b = data_loader.get_price_series(pair['asset_b'], days=lookback_days, db=None)
        
        if len(price_a) < 50 or len(price_b) < 50:
            raise HTTPException(status_code=400, detail="Insufficient data for chart")
        
        # Calculate spread using ROLLING beta/alpha (same as backtester)
        from app.modules.screener.cointegration import CointegrationTester
        from statsmodels.regression.linear_model import OLS
        import numpy as np
        import pandas as pd
        
        # Align price series
        aligned = pd.DataFrame({'a': price_a, 'b': price_b}).dropna()
        
        # Calculate rolling z-score with rolling beta/alpha (60-day window for z-score, 90-day for beta)
        rolling_zscore_list = []
        rolling_spread_list = []
        rolling_dates = []
        
        for i in range(len(aligned)):
            # Calculate rolling beta/alpha using last 90 days
            beta_window = min(90, i + 1)
            if beta_window >= 30:  # Need minimum data
                historical_data = aligned.iloc[max(0, i+1-beta_window):i+1]
                
                try:
                    X = historical_data['b'].values.reshape(-1, 1)
                    y = historical_data['a'].values
                    X_with_const = np.column_stack([np.ones(len(X)), X])
                    model = OLS(y, X_with_const).fit()
                    rolling_beta = float(model.params[1])
                    rolling_alpha = float(model.params[0])
                    
                    # Validate beta
                    if rolling_beta <= 0 or rolling_beta > 10:
                        continue
                    
                    # Calculate rolling z-score using last 60 days with this beta/alpha
                    spread_window = min(60, i + 1)
                    if spread_window >= 30:
                        spread_data = aligned.iloc[max(0, i+1-spread_window):i+1]
                        current_spread = CointegrationTester.calculate_spread(
                            spread_data['a'],
                            spread_data['b'],
                            rolling_beta,
                            rolling_alpha
                        )
                        current_zscore_series = CointegrationTester.calculate_zscore(current_spread)
                        if len(current_zscore_series) > 0:
                            rolling_zscore_list.append(float(current_zscore_series.iloc[-1]))
                            rolling_spread_list.append(float(current_spread.iloc[-1]))
                            rolling_dates.append(aligned.index[i])
                except Exception:
                    continue
        
        # Convert to pandas Series
        if len(rolling_zscore_list) > 0:
            zscore = pd.Series(rolling_zscore_list, index=rolling_dates)
            spread = pd.Series(rolling_spread_list, index=rolling_dates)
        else:
            # Fallback to global beta if rolling calculation fails
            X = aligned['b'].values.reshape(-1, 1)
            y = aligned['a'].values
            X_with_const = np.column_stack([np.ones(len(X)), X])
            model = OLS(y, X_with_const).fit()
            alpha = model.params[0]
            beta = pair['beta']
            spread = CointegrationTester.calculate_spread(price_a, price_b, beta, alpha)
            zscore = CointegrationTester.calculate_zscore(spread)
        
        # Align all series
        aligned_data = pd.DataFrame({
            'spread': spread,
            'zscore': zscore
        }).dropna()
        
        # Calculate hedged price B using last known beta/alpha (or global as fallback)
        # Get the last beta/alpha from rolling calculation
        if len(rolling_zscore_list) > 0:
            # Use last rolling beta/alpha
            last_window_data = aligned.iloc[-90:] if len(aligned) >= 90 else aligned
            try:
                X = last_window_data['b'].values.reshape(-1, 1)
                y = last_window_data['a'].values
                X_with_const = np.column_stack([np.ones(len(X)), X])
                model = OLS(y, X_with_const).fit()
                last_alpha = model.params[0]
                last_beta = model.params[1]
            except Exception as e:
                logger.warning(f"Rolling OLS for hedged price failed, using fallback beta/alpha: {e}")
                last_alpha = pair.get('alpha', 0)
                last_beta = pair['beta']
        else:
            last_alpha = pair.get('alpha', 0)
            last_beta = pair['beta']
        
        hedged_price_b = last_alpha + last_beta * price_b
        
        # Align raw prices with spread data first, then normalize
        raw_prices_aligned = pd.DataFrame({
            'price_a': price_a,
            'price_b': price_b,
            'hedged_price_b': hedged_price_b
        }).dropna()
        
        # Normalize prices AFTER dropna to ensure they start at 100
        price_a_normalized = (raw_prices_aligned['price_a'] / raw_prices_aligned['price_a'].iloc[0] * 100) if len(raw_prices_aligned) > 0 and raw_prices_aligned['price_a'].iloc[0] != 0 else raw_prices_aligned['price_a']
        price_b_normalized = (raw_prices_aligned['price_b'] / raw_prices_aligned['price_b'].iloc[0] * 100) if len(raw_prices_aligned) > 0 and raw_prices_aligned['price_b'].iloc[0] != 0 else raw_prices_aligned['price_b']
        hedged_price_b_normalized = (raw_prices_aligned['hedged_price_b'] / raw_prices_aligned['hedged_price_b'].iloc[0] * 100) if len(raw_prices_aligned) > 0 and raw_prices_aligned['hedged_price_b'].iloc[0] != 0 else raw_prices_aligned['hedged_price_b']
        
        normalized_prices_aligned = pd.DataFrame({
            'price_a_norm': price_a_normalized,
            'price_b_norm': price_b_normalized,
            'hedged_price_b_norm': hedged_price_b_normalized
        })
        
        # Find crossing points (±2σ) for markers
        crossing_points = []
        zscore_values = zscore.values
        zscore_index = zscore.index
        
        for i in range(1, len(zscore_values)):
            prev_z = zscore_values[i-1]
            curr_z = zscore_values[i]
            
            # Crossing +2σ (going up)
            if prev_z <= 2 and curr_z > 2:
                crossing_points.append({
                    'date': zscore_index[i].isoformat() if hasattr(zscore_index[i], 'isoformat') else str(zscore_index[i]),
                    'type': 'entry_high',
                    'zscore': float(curr_z)
                })
            # Crossing -2σ (going down)
            elif prev_z >= -2 and curr_z < -2:
                crossing_points.append({
                    'date': zscore_index[i].isoformat() if hasattr(zscore_index[i], 'isoformat') else str(zscore_index[i]),
                    'type': 'entry_low',
                    'zscore': float(curr_z)
                })
            # Crossing back to mean from high
            elif prev_z > 2 and curr_z <= 2:
                crossing_points.append({
                    'date': zscore_index[i].isoformat() if hasattr(zscore_index[i], 'isoformat') else str(zscore_index[i]),
                    'type': 'exit_high',
                    'zscore': float(curr_z)
                })
            # Crossing back to mean from low
            elif prev_z < -2 and curr_z >= -2:
                crossing_points.append({
                    'date': zscore_index[i].isoformat() if hasattr(zscore_index[i], 'isoformat') else str(zscore_index[i]),
                    'type': 'exit_low',
                    'zscore': float(curr_z)
                })
        
        # Convert to list of dicts for JSON response
        chart_data = []
        for date, row in aligned_data.iterrows():
            # Get normalized prices for this date
            price_a_norm = None
            price_b_norm = None
            price_b_hedged_norm = None
            if date in normalized_prices_aligned.index:
                price_a_norm = float(normalized_prices_aligned.loc[date, 'price_a_norm'])
                price_b_norm = float(normalized_prices_aligned.loc[date, 'price_b_norm'])
                price_b_hedged_norm = float(normalized_prices_aligned.loc[date, 'hedged_price_b_norm'])
            
            chart_data.append({
                'date': date.isoformat() if hasattr(date, 'isoformat') else str(date),
                'spread': float(row['spread']),
                'zscore': float(row['zscore']),
                'price_a_norm': price_a_norm,
                'price_b_norm': price_b_norm,
                'price_b_hedged_norm': price_b_hedged_norm
            })
        
        # Calculate statistics
        mean_spread = float(spread.mean())
        std_spread = float(spread.std())
        
        # Calculate normalized spread statistics (as percentage of mean, if mean != 0)
        if abs(mean_spread) > 1e-10:  # Avoid division by zero
            spread_min_pct = float((spread.min() - mean_spread) / abs(mean_spread) * 100)
            spread_max_pct = float((spread.max() - mean_spread) / abs(mean_spread) * 100)
            spread_std_pct = float(std_spread / abs(mean_spread) * 100)
        else:
            # If mean is near zero, use absolute values
            spread_min_pct = None
            spread_max_pct = None
            spread_std_pct = None
        
        # Calculate additional metrics
        current_zscore = float(zscore.iloc[-1]) if len(zscore) > 0 else 0.0
        min_zscore = float(zscore.min()) if len(zscore) > 0 else 0.0
        max_zscore = float(zscore.max()) if len(zscore) > 0 else 0.0
        min_spread = float(spread.min())
        max_spread = float(spread.max())
        
        # Calculate composite score (pair strength indicator)
        # Higher correlation + lower ADF p-value + lower Hurst = better pair
        hurst = pair.get('hurst_exponent', 0.5)
        if hurst is None:
            hurst = 0.5
        
        correlation_score = pair['correlation']  # 0-1
        adf_score = 1.0 - (pair['adf_pvalue'] / 0.1)  # 0-1 (better if lower p-value)
        hurst_score = 1.0 - abs(hurst - 0.5) * 2  # 0-1 (better if closer to 0.5)
        
        composite_score = (correlation_score * 0.5 + adf_score * 0.3 + hurst_score * 0.2) * 100
        
        # ========== MEAN REVERSION STATISTICS ==========
        import scipy.stats as stats
        
        # 1. Half-life calculation (time for spread to revert halfway to mean)
        def calculate_half_life(spread_series):
            """Calculate half-life of mean reversion using OLS"""
            spread_clean = spread_series.dropna()
            if len(spread_clean) < 10:
                return None
            
            spread_lag = spread_clean.shift(1).dropna()
            spread_diff = spread_clean.diff().dropna()
            
            # Align series
            aligned = pd.DataFrame({
                'spread': spread_clean[1:],
                'spread_lag': spread_lag[1:],
                'spread_diff': spread_diff[1:]
            }).dropna()
            
            if len(aligned) < 10:
                return None
            
            # OLS: spread_diff = theta * spread_lag + error
            X = aligned['spread_lag'].values.reshape(-1, 1)
            y = aligned['spread_diff'].values
            model = OLS(y, X).fit()
            theta = model.params[0]
            
            if theta >= 0:
                return None  # Not mean reverting
            
            half_life = -np.log(2) / theta
            return max(0, half_life)  # Days
        
        half_life = calculate_half_life(spread)
        
        # 2. Time outside bands statistics
        zscore_abs = zscore.abs()
        time_outside_1sigma = (zscore_abs > 1).sum() / len(zscore) * 100 if len(zscore) > 0 else 0
        time_outside_2sigma = (zscore_abs > 2).sum() / len(zscore) * 100 if len(zscore) > 0 else 0
        time_outside_3sigma = (zscore_abs > 3).sum() / len(zscore) * 100 if len(zscore) > 0 else 0
        
        # 3. Mean reversion events (crossings of mean)
        mean_crossings = ((zscore.shift(1) > 0) & (zscore <= 0)).sum() + \
                         ((zscore.shift(1) < 0) & (zscore >= 0)).sum()
        
        # 4. Average time to mean reversion
        def calculate_avg_reversion_time(zscore_series):
            """Calculate average days to return to mean (|z| < 0.5)"""
            reversion_times = []
            in_deviation = False
            deviation_start = None
            
            for i, z in enumerate(zscore_series):
                if abs(z) > 0.5 and not in_deviation:
                    in_deviation = True
                    deviation_start = i
                elif abs(z) <= 0.5 and in_deviation:
                    in_deviation = False
                    reversion_times.append(i - deviation_start)
            
            return np.mean(reversion_times) if reversion_times else None
        
        avg_reversion_time = calculate_avg_reversion_time(zscore)
        
        # ========== CURRENT DEVIATION ANALYSIS ==========
        # 5. Current z-score percentile (how rare is current deviation)
        current_zscore_percentile = float(stats.percentileofscore(zscore.values, current_zscore)) if len(zscore) > 0 else 50.0
        
        # Determine rarity
        abs_current_z = abs(current_zscore)
        if abs_current_z >= 3:
            current_zscore_rarity = "Very Rare"
        elif abs_current_z >= 2:
            current_zscore_rarity = "Rare"
        elif abs_current_z >= 1:
            current_zscore_rarity = "Uncommon"
        else:
            current_zscore_rarity = "Common"
        
        # Probability of extreme event (two-tailed)
        probability_extreme = float(stats.norm.sf(abs_current_z) * 2 * 100) if abs_current_z > 0 else 100.0
        
        # ========== EXPECTED RETURN ANALYSIS ==========
        # 6. Expected return based on historical behavior
        # Note: Analysis uses full lookback_days period (e.g., 365 days for crypto), 
        # but forecasts returns for lookforward_days (5 days) ahead
        def calculate_expected_return(zscore_series, spread_series, current_z, lookforward_days=5):
            """
            Calculate expected return based on historical behavior
            
            Analysis period: lookback_days (e.g., 365 days from settings for crypto)
            Forecast horizon: lookforward_days (default 5 days ahead)
            """
            # Find similar z-score periods
            threshold = 0.5  # Within 0.5 z-score units
            similar_periods = zscore_series[abs(zscore_series - current_z) < threshold]
            
            if len(similar_periods) < 10:
                return None
            
            returns = []
            for idx in similar_periods.index[:100]:  # Limit to first 100 for performance
                try:
                    idx_pos = spread_series.index.get_loc(idx)
                    if idx_pos + lookforward_days < len(spread_series):
                        future_idx = spread_series.index[idx_pos + lookforward_days]
                        current_spread_val = spread_series.loc[idx]
                        future_spread_val = spread_series.loc[future_idx]
                        
                        # Calculate return based on mean reversion expectation
                        if current_z > 0:  # Expect mean reversion down
                            ret = (current_spread_val - future_spread_val) / abs(current_spread_val) if abs(current_spread_val) > 0 else 0
                        else:  # Expect mean reversion up
                            ret = (future_spread_val - current_spread_val) / abs(current_spread_val) if abs(current_spread_val) > 0 else 0
                        returns.append(ret)
                except (KeyError, IndexError):
                    continue
            
            if returns and len(returns) >= 5:
                return {
                    'expected_return_5d': float(np.mean(returns) * 100),
                    'expected_return_std': float(np.std(returns) * 100),
                    'win_rate': float((np.array(returns) > 0).sum() / len(returns) * 100),
                    'sample_size': len(returns)
                }
            return None
        
        expected_return = calculate_expected_return(zscore, spread, current_zscore)
        
        # ========== RISK METRICS ==========
        # Use z-score based metrics (more stable and interpretable than spread percentage)
        # Spread can be near zero, causing huge percentage changes
        
        # 7. VaR (Value at Risk) - 95% confidence
        # Daily z-score change at 5th percentile (worst case daily move)
        zscore_changes = zscore.diff().dropna()
        var_95 = float(np.percentile(zscore_changes, 5)) if len(zscore_changes) > 0 else 0.0  # In z-score units
        
        # 8. Maximum drawdown - maximum deviation from mean (in z-score units)
        # This represents the worst historical deviation from the mean
        if len(zscore) > 0:
            max_drawdown = float(zscore.abs().max())  # Maximum absolute z-score reached
        else:
            max_drawdown = 0.0
        
        # 9. Volatility of z-score changes (annualized, in z-score units)
        # Represents how volatile the mean reversion process is
        volatility_annual = float(zscore_changes.std() * np.sqrt(365)) if len(zscore_changes) > 0 else 0.0  # 365 for crypto
        
        # ========== RETURN PROBABILITIES BY Z-SCORE ZONE ==========
        # 10. Return probability by z-score zone
        def calculate_return_probabilities(zscore_series, spread_series, lookforward_days=5):
            """Calculate probability of profitable return by z-score zone"""
            zones = {
                'extreme_high': (zscore_series > 2),
                'high': (zscore_series > 1) & (zscore_series <= 2),
                'neutral': (zscore_series.abs() <= 1),
                'low': (zscore_series < -1) & (zscore_series >= -2),
                'extreme_low': (zscore_series < -2)
            }
            
            probabilities = {}
            sample_sizes = {}
            for zone_name, mask in zones.items():
                indices = zscore_series[mask].index
                if len(indices) < 5:
                    probabilities[zone_name] = None
                    sample_sizes[zone_name] = 0
                    continue
                
                profitable = 0
                total = 0
                for idx in indices[:100]:  # Limit to first 100 for performance
                    try:
                        idx_pos = spread_series.index.get_loc(idx)
                        if idx_pos + lookforward_days < len(spread_series):
                            future_idx = spread_series.index[idx_pos + lookforward_days]
                            current_val = spread_series.loc[idx]
                            future_val = spread_series.loc[future_idx]
                            
                            # For high z-score, expect spread to decrease (mean reversion)
                            # For low z-score, expect spread to increase (mean reversion)
                            if zone_name in ['extreme_high', 'high']:
                                if future_val < current_val:
                                    profitable += 1
                            elif zone_name in ['extreme_low', 'low']:
                                if future_val > current_val:
                                    profitable += 1
                            total += 1
                    except (KeyError, IndexError):
                        continue
                
                probabilities[zone_name] = float(profitable / total * 100) if total > 0 else None
                sample_sizes[zone_name] = total
            
            return {
                'probabilities': probabilities,
                'sample_sizes': sample_sizes
            }
        
        return_probabilities_data = calculate_return_probabilities(zscore, spread)
        
        # ========== BUILD RESPONSE ==========
        return {
            'pair_id': pair_id,
            'asset_a': pair['asset_a'],
            'asset_b': pair['asset_b'],
            'beta': pair['beta'],
            'mean_spread': mean_spread,
            'std_spread': std_spread,
            'current_zscore': current_zscore,
            'min_zscore': min_zscore,
            'max_zscore': max_zscore,
            'min_spread': min_spread,
            'max_spread': max_spread,
            'composite_score': composite_score,
            'data': chart_data,
            'crossing_points': crossing_points,  # Points where z-score crosses ±2σ
            # Spread statistics with normalized values
            'spread_statistics': {
                'mean': mean_spread,
                'std': std_spread,
                'min': min_spread,
                'max': max_spread,
                'std_pct': spread_std_pct,  # Normalized std as % of mean
                'min_pct': spread_min_pct,  # Min as % deviation from mean
                'max_pct': spread_max_pct   # Max as % deviation from mean
            },
            # Mean reversion statistics
            'mean_reversion': {
                'half_life_days': float(half_life) if half_life else None,
                'mean_crossings': int(mean_crossings),
                'time_outside_1sigma_pct': float(time_outside_1sigma),
                'time_outside_2sigma_pct': float(time_outside_2sigma),
                'time_outside_3sigma_pct': float(time_outside_3sigma),
                'avg_reversion_time_days': float(avg_reversion_time) if avg_reversion_time else None
            },
            # Current deviation analysis
            'current_deviation': {
                'zscore_percentile': current_zscore_percentile,
                'rarity': current_zscore_rarity,
                'probability_extreme': probability_extreme
            },
            # Expected return
            'expected_return': expected_return if expected_return else None,
            # Risk metrics (in z-score units)
            'risk_metrics': {
                'var_95': var_95,  # Daily z-score change at 5th percentile
                'max_drawdown': max_drawdown,  # Maximum absolute z-score
                'volatility_annual': volatility_annual  # Annualized z-score volatility
            },
            # Return probabilities by zone
            'return_probabilities': return_probabilities_data['probabilities'],
            'return_probabilities_samples': return_probabilities_data['sample_sizes']
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting pair spread data: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.post("/calculate-position", response_model=PositionCalculationResponse)
async def calculate_position(request: PositionCalculationRequest):
    """Calculate position sizes for a pair based on beta and capital"""
    try:
        from app.modules.calculator.position_calculator import PositionCalculator, PositionStrategy
        from app.modules.screener.data_loader import DataLoader
        
        live_screener = get_live_screener()
        results = live_screener.get_results()
        
        # Find pair by ID
        pair = None
        for idx, result in enumerate(results):
            if result.get('id') == request.pair_id or (idx + 1) == request.pair_id:
                pair = result
                break
        
        if not pair:
            raise HTTPException(status_code=404, detail="Pair not found")
        
        # Get current prices
        data_loader = DataLoader()
        try:
            # Get latest price from exchange
            ticker_a = data_loader.exchange.fetch_ticker(f"{pair['asset_a']}/USDT")
            ticker_b = data_loader.exchange.fetch_ticker(f"{pair['asset_b']}/USDT")
            price_a = ticker_a['last'] or ticker_a['close']
            price_b = ticker_b['last'] or ticker_b['close']
        except Exception as e:
            logger.warning(f"Could not fetch current prices: {e}, using last known prices")
            # Fallback: get last price from price series
            price_series_a = data_loader.get_price_series(pair['asset_a'], days=1, db=None)
            price_series_b = data_loader.get_price_series(pair['asset_b'], days=1, db=None)
            if len(price_series_a) > 0 and len(price_series_b) > 0:
                price_a = float(price_series_a.iloc[-1])
                price_b = float(price_series_b.iloc[-1])
            else:
                raise HTTPException(status_code=400, detail="Could not determine current prices")
        
        # Get current Z-Score
        zscore = pair.get('current_zscore', 0.0) or 0.0
        
        # Parse strategy
        strategy_map = {
            "dollar_neutral": PositionStrategy.DOLLAR_NEUTRAL,
            "equal_dollar": PositionStrategy.EQUAL_DOLLAR,
            "long_asset_a": PositionStrategy.LONG_ASSET_A,
            "long_asset_b": PositionStrategy.LONG_ASSET_B
        }
        strategy = strategy_map.get(request.strategy, PositionStrategy.DOLLAR_NEUTRAL)
        
        # Calculate position
        position = PositionCalculator.calculate_position(
            capital=request.capital,
            beta=pair['beta'],
            asset_a_price=price_a,
            asset_b_price=price_b,
            strategy=strategy,
            zscore=zscore
        )
        
        # Convert to response format
        return PositionCalculationResponse(
            asset_a=AssetPosition(**position['asset_a']),
            asset_b=AssetPosition(**position['asset_b']),
            total_capital=position['total_capital'],
            strategy=position['strategy'],
            beta=position['beta'],
            zscore=position['zscore'],
            net_exposure=position['net_exposure']
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating position: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.get("/pairs/{pair_id}/history")
async def get_pair_history(pair_id: int):
    """Get history of a specific pair across screening sessions"""
    try:
        from app.modules.history.history_analyzer import HistoryAnalyzer
        
        live_screener = get_live_screener()
        history = live_screener.get_history()
        
        # Find pair in all historical sessions
        pair_history = []
        for session in history:
            results = session.get('results', [])
            for result in results:
                result_id = result.get('id')
                if result_id == pair_id or (result.get('asset_a') and result.get('asset_b')):
                    # Check if this is the pair we're looking for
                    # We need to match by assets since IDs might change
                    pair = None
                    for idx, r in enumerate(results):
                        if r.get('id') == pair_id or (idx + 1) == pair_id:
                            pair = r
                            break
                    
                    if pair:
                        pair_history.append({
                            'timestamp': session.get('timestamp'),
                            'correlation': pair.get('correlation'),
                            'beta': pair.get('beta'),
                            'adf_pvalue': pair.get('adf_pvalue'),
                            'current_zscore': pair.get('current_zscore'),
                            'composite_score': pair.get('composite_score')
                        })
                        break
        
        return {
            'pair_id': pair_id,
            'history': pair_history,
            'total_sessions': len(pair_history)
        }
    except Exception as e:
        logger.error(f"Error getting pair history: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.get("/trends")
async def get_trends():
    """Get trends across all screening sessions"""
    try:
        from app.modules.history.history_analyzer import HistoryAnalyzer
        
        live_screener = get_live_screener()
        history = live_screener.get_history()
        
        analyzer = HistoryAnalyzer()
        trends = analyzer.analyze_trends(history)
        
        return trends
    except Exception as e:
        logger.error(f"Error getting trends: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.get("/comparison")
async def compare_periods():
    """Compare current results with previous screening session"""
    try:
        from app.modules.history.history_analyzer import HistoryAnalyzer
        
        live_screener = get_live_screener()
        current_results = live_screener.get_results()
        history = live_screener.get_history()
        
        if not history:
            return {
                'changes': [],
                'message': 'No previous sessions to compare'
            }
        
        # Get most recent previous session
        previous_results = history[-1].get('results', [])
        
        analyzer = HistoryAnalyzer()
        changes = analyzer.calculate_metric_changes(current_results, previous_results)
        
        return {
            'changes': changes,
            'current_count': len(current_results),
            'previous_count': len(previous_results),
            'comparison_date': history[-1].get('timestamp')
        }
    except Exception as e:
        logger.error(f"Error comparing periods: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.get("/export/csv")
async def export_results_csv(
    limit: int = 1000,
    min_correlation: Optional[float] = None
):
    """Export screening results to CSV"""
    try:
        live_screener = get_live_screener()
        results = live_screener.get_results()
        
        # Filter if needed
        if min_correlation:
            results = [r for r in results if r.get('correlation', 0) >= min_correlation]
        
        # Limit
        results = results[:limit]
        
        # Convert to DataFrame
        df = pd.DataFrame(results)
        
        # Select relevant columns
        columns = [
            'asset_a', 'asset_b', 'correlation', 'beta', 'adf_pvalue',
            'spread_std', 'hurst_exponent', 'mean_spread', 'current_zscore',
            'composite_score'
        ]
        available_columns = [col for col in columns if col in df.columns]
        df = df[available_columns]
        
        # Convert to CSV
        output = io.StringIO()
        df.to_csv(output, index=False)
        output.seek(0)
        
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=pairs_screener_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"}
        )
    except Exception as e:
        logger.error(f"Error exporting CSV: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.get("/export/excel")
async def export_results_excel(
    limit: int = 1000,
    min_correlation: Optional[float] = None
):
    """Export screening results to Excel"""
    try:
        live_screener = get_live_screener()
        results = live_screener.get_results()
        
        # Filter if needed
        if min_correlation:
            results = [r for r in results if r.get('correlation', 0) >= min_correlation]
        
        # Limit
        results = results[:limit]
        
        # Convert to DataFrame
        df = pd.DataFrame(results)
        
        # Select relevant columns
        columns = [
            'asset_a', 'asset_b', 'correlation', 'beta', 'adf_pvalue',
            'spread_std', 'hurst_exponent', 'mean_spread', 'current_zscore',
            'composite_score'
        ]
        available_columns = [col for col in columns if col in df.columns]
        df = df[available_columns]
        
        # Convert to Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Pairs')
        output.seek(0)
        
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=pairs_screener_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"}
        )
    except Exception as e:
        logger.error(f"Error exporting Excel: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.get("/pairs/{pair_id}/export")
async def export_pair_data(pair_id: int, format: str = "csv"):
    """Export specific pair data"""
    try:
        live_screener = get_live_screener()
        results = live_screener.get_results()
        
        # Find pair
        pair = None
        for idx, result in enumerate(results):
            if result.get('id') == pair_id or (idx + 1) == pair_id:
                pair = result
                break
        
        if not pair:
            raise HTTPException(status_code=404, detail="Pair not found")
        
        # Get spread data
        spread_data = None
        try:
            from app.modules.screener.screener import PairsScreener
            from app.modules.screener.data_loader import DataLoader
            from app.config import settings
            
            data_loader = DataLoader()
            lookback_days = pair.get('lookback_days', settings.SCREENER_LOOKBACK_DAYS)
            
            price_a = data_loader.get_price_series(pair['asset_a'], days=lookback_days, db=None)
            price_b = data_loader.get_price_series(pair['asset_b'], days=lookback_days, db=None)
            
            if len(price_a) >= 50 and len(price_b) >= 50:
                from app.modules.screener.cointegration import CointegrationTester
                from statsmodels.regression.linear_model import OLS
                import numpy as np
                import pandas as pd
                
                aligned = pd.DataFrame({'a': price_a, 'b': price_b}).dropna()
                X = aligned['b'].values.reshape(-1, 1)
                y = aligned['a'].values
                X_with_const = np.column_stack([np.ones(len(X)), X])
                model = OLS(y, X_with_const).fit()
                alpha = model.params[0]
                beta = pair['beta']
                
                spread = CointegrationTester.calculate_spread(price_a, price_b, beta, alpha)
                zscore = CointegrationTester.calculate_zscore(spread)
                
                aligned_data = pd.DataFrame({
                    'date': spread.index,
                    'spread': spread.values,
                    'zscore': zscore.values
                })
                spread_data = aligned_data
        except Exception as e:
            logger.warning(f"Could not load spread data for export: {e}")
        
        if format.lower() == "csv":
            if spread_data is not None:
                output = io.StringIO()
                spread_data.to_csv(output, index=False)
                output.seek(0)
                return StreamingResponse(
                    iter([output.getvalue()]),
                    media_type="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=pair_{pair['asset_a']}_{pair['asset_b']}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"}
                )
            else:
                # Export just pair info
                df = pd.DataFrame([pair])
                output = io.StringIO()
                df.to_csv(output, index=False)
                output.seek(0)
                return StreamingResponse(
                    iter([output.getvalue()]),
                    media_type="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=pair_{pair['asset_a']}_{pair['asset_b']}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"}
                )
        else:
            raise HTTPException(status_code=400, detail="Only CSV format supported for pair export")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting pair data: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

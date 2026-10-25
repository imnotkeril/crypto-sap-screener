"""
FastAPI routes for backtesting
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional, Literal
from datetime import datetime
from pydantic import BaseModel, Field

from app.modules.backtester.backtester import Backtester
from app.modules.backtester.strategy import ZScoreStrategy
from sqlalchemy.orm import Session
from app.database import get_db
from app.database import BacktestSession as DbBacktestSession
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# In-memory storage for backtest sessions (since we're not using DB)
_backtest_sessions = {}
_next_session_id = 1


class BacktestRequest(BaseModel):
    """Request for running a backtest"""
    asset_a: str
    asset_b: str
    entry_threshold: float = Field(default=2.0, ge=0.5, le=5.0)
    stop_loss: Optional[float] = None
    stop_loss_type: Literal['none', 'zscore', 'percent', 'atr'] = Field(default='percent')
    take_profit: Optional[float] = Field(default=3.0)
    take_profit_type: Literal['zscore', 'percent', 'atr'] = Field(default='percent')
    initial_capital: float = Field(default=10000.0, gt=0)
    position_size_pct: float = Field(default=100.0, ge=1.0, le=100.0, description="Percentage of capital to use per trade (1-100%)")
    lookback_days: int = Field(default=365, ge=50, le=1000)
    beta: Optional[float] = None
    transaction_cost_pct: float = Field(default=0.001, ge=0.0, le=0.05, description="Transaction cost for ALL trades (entry/exit/rebalancing) as % of notional")
    enable_rebalancing: bool = Field(default=False, description="Enable dynamic hedge rebalancing")
    rebalancing_frequency_days: int = Field(default=5, ge=1, le=30, description="Minimum days between rebalances")
    rebalancing_threshold: float = Field(default=0.05, ge=0.01, le=0.5, description="Minimum beta drift % to trigger rebalance")


@router.post("/run")
async def run_backtest(request: BacktestRequest, db: Session = Depends(get_db)):
    """Run a backtest for a pair"""
    try:
        strategy = ZScoreStrategy(
            entry_threshold=request.entry_threshold,
            stop_loss=request.stop_loss,
            stop_loss_type=request.stop_loss_type,
            take_profit=request.take_profit,
            take_profit_type=request.take_profit_type,
            enable_rebalancing=request.enable_rebalancing,
            rebalancing_frequency_days=request.rebalancing_frequency_days,
            rebalancing_threshold=request.rebalancing_threshold,
        )
        
        backtester = Backtester(
            initial_capital=request.initial_capital,
            transaction_cost_pct=request.transaction_cost_pct
        )
        results = backtester.run_backtest(
            asset_a=request.asset_a,
            asset_b=request.asset_b,
            strategy=strategy,
            lookback_days=request.lookback_days,
            beta=request.beta,
            position_size_pct=request.position_size_pct
        )

        # Persist to DB if available; fallback to in-memory otherwise.
        if db is not None:
            # #region agent log
            import pandas as pd
            def _has_timestamp(obj, path=""):
                """Check if object contains Timestamp objects"""
                if isinstance(obj, pd.Timestamp):
                    return [path]
                elif isinstance(obj, dict):
                    found = []
                    for k, v in obj.items():
                        found.extend(_has_timestamp(v, f"{path}.{k}" if path else k))
                    return found
                elif isinstance(obj, (list, tuple)):
                    found = []
                    for i, item in enumerate(obj):
                        found.extend(_has_timestamp(item, f"{path}[{i}]"))
                    return found
                return []
            timestamp_paths = _has_timestamp(results)
            
            row = DbBacktestSession(
                asset_a=request.asset_a,
                asset_b=request.asset_b,
                strategy_type="zscore",
                entry_threshold=request.entry_threshold,
                exit_threshold=None,
                initial_capital=request.initial_capital,
                start_date=None,
                end_date=None,
                request=request.model_dump(),
                results=results,
                created_at=datetime.utcnow(),
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return {"session_id": row.id, "results": results}

        global _next_session_id, _backtest_sessions
        session_id = _next_session_id
        _next_session_id += 1
        _backtest_sessions[session_id] = {
            'id': session_id,
            'asset_a': request.asset_a,
            'asset_b': request.asset_b,
            'strategy_type': 'zscore',
            'entry_threshold': request.entry_threshold,
            'stop_loss': request.stop_loss,
            'stop_loss_type': request.stop_loss_type,
            'take_profit': request.take_profit,
            'take_profit_type': request.take_profit_type,
            'initial_capital': request.initial_capital,
            'created_at': datetime.utcnow().isoformat(),
            'results': results
        }
        return {'session_id': session_id, 'results': results}
    except Exception as e:
        logger.error(f"Error running backtest: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/results/{session_id}")
async def get_backtest_results(session_id: int, db: Session = Depends(get_db)):
    """Get backtest results by session ID"""
    try:
        if db is not None:
            row = db.query(DbBacktestSession).filter(DbBacktestSession.id == session_id).first()
            if not row:
                raise HTTPException(status_code=404, detail="Backtest session not found")
            return row.results or {}

        if session_id not in _backtest_sessions:
            raise HTTPException(status_code=404, detail="Backtest session not found")
        
        session = _backtest_sessions[session_id]
        return session['results']
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting backtest results: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/sessions")
async def get_backtest_sessions(db: Session = Depends(get_db)):
    """Get list of all backtest sessions"""
    try:
        if db is not None:
            rows = db.query(DbBacktestSession).order_by(DbBacktestSession.created_at.desc()).all()
            sessions = []
            for s in rows:
                req = s.request or {}
                sessions.append({
                    "id": s.id,
                    "asset_a": s.asset_a,
                    "asset_b": s.asset_b,
                    "strategy_type": s.strategy_type,
                    "entry_threshold": s.entry_threshold,
                    "stop_loss": req.get("stop_loss"),
                    "stop_loss_type": req.get("stop_loss_type"),
                    "take_profit": req.get("take_profit"),
                    "take_profit_type": req.get("take_profit_type"),
                    "initial_capital": s.initial_capital,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                    "metrics": (s.results or {}).get("metrics", {}),
                })
            return {"sessions": sessions, "total": len(sessions)}

        sessions = []
        for session_id, session in _backtest_sessions.items():
            sessions.append({
                'id': session['id'],
                'asset_a': session['asset_a'],
                'asset_b': session['asset_b'],
                'strategy_type': session['strategy_type'],
                'entry_threshold': session['entry_threshold'],
                'stop_loss': session.get('stop_loss'),
                'stop_loss_type': session.get('stop_loss_type', 'percent'),
                'take_profit': session.get('take_profit'),
                'take_profit_type': session.get('take_profit_type', 'percent'),
                'initial_capital': session['initial_capital'],
                'created_at': session['created_at'],
                'metrics': session['results']['metrics']
            })
        
        return {
            'sessions': sessions,
            'total': len(sessions)
        }
    except Exception as e:
        logger.error(f"Error getting backtest sessions: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


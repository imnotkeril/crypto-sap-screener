"""
FastAPI routes for positions management
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.database import Position as DbPosition
from app.modules.positions.position_manager import PositionManager
import logging

from app.api.validation import ensure_pair_exists
router = APIRouter()
logger = logging.getLogger(__name__)

# Global position manager instance
_position_manager: Optional[PositionManager] = None


def get_position_manager() -> PositionManager:
    """Get or create global position manager instance"""
    global _position_manager
    if _position_manager is None:
        _position_manager = PositionManager()
    return _position_manager


class CreatePositionRequest(BaseModel):
    """Request for creating a position"""
    pair_id: int
    asset_a: str
    asset_b: str
    side: str = Field(..., pattern="^(long|short)$")
    quantity_a: float = Field(gt=0)
    quantity_b: float = Field(gt=0)
    entry_price_a: float = Field(gt=0)
    entry_price_b: float = Field(gt=0)
    beta: float = Field(gt=0)
    entry_zscore: float


@router.post("/")
async def create_position(request: CreatePositionRequest, db: Session = Depends(get_db)):
    """Create a new position"""
    ensure_pair_exists(db, request.pair_id, request.asset_a, request.asset_b)
    try:
        if db is not None:
            row = DbPosition(
                pair_id=request.pair_id,
                asset_a=request.asset_a,
                asset_b=request.asset_b,
                side=request.side,
                quantity_a=request.quantity_a,
                quantity_b=request.quantity_b,
                entry_price_a=request.entry_price_a,
                entry_price_b=request.entry_price_b,
                beta=request.beta,
                entry_zscore=request.entry_zscore,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return {
                "position_id": row.id,
                "pair_id": row.pair_id,
                "asset_a": row.asset_a,
                "asset_b": row.asset_b,
                "side": row.side,
                "quantity_a": row.quantity_a,
                "quantity_b": row.quantity_b,
                "entry_price_a": row.entry_price_a,
                "entry_price_b": row.entry_price_b,
                "beta": row.beta,
                "entry_zscore": row.entry_zscore,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }

        manager = get_position_manager()
        position = manager.create_position(
            pair_id=request.pair_id,
            asset_a=request.asset_a,
            asset_b=request.asset_b,
            side=request.side,
            quantity_a=request.quantity_a,
            quantity_b=request.quantity_b,
            entry_price_a=request.entry_price_a,
            entry_price_b=request.entry_price_b,
            beta=request.beta,
            entry_zscore=request.entry_zscore
        )
        return position.to_dict()
    except Exception as e:
        logger.error(f"Error creating position: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/")
async def get_positions(db: Session = Depends(get_db)):
    """Get all positions"""
    try:
        if db is not None:
            rows = db.query(DbPosition).order_by(DbPosition.created_at.desc()).all()
            positions = []
            for row in rows:
                positions.append({
                    "position_id": row.id,
                    "pair_id": row.pair_id,
                    "asset_a": row.asset_a,
                    "asset_b": row.asset_b,
                    "side": row.side,
                    "quantity_a": row.quantity_a,
                    "quantity_b": row.quantity_b,
                    "entry_price_a": row.entry_price_a,
                    "entry_price_b": row.entry_price_b,
                    "beta": row.beta,
                    "entry_zscore": row.entry_zscore,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                })
            return {"positions": positions, "total": len(positions)}

        manager = get_position_manager()
        positions = manager.get_positions()
        return {
            'positions': [p.to_dict() for p in positions],
            'total': len(positions)
        }
    except Exception as e:
        logger.error(f"Error getting positions: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{position_id}")
async def get_position(position_id: int, db: Session = Depends(get_db)):
    """Get position by ID"""
    try:
        if db is not None:
            row = db.query(DbPosition).filter(DbPosition.id == position_id).first()
            if not row:
                raise HTTPException(status_code=404, detail="Position not found")
            return {
                "position_id": row.id,
                "pair_id": row.pair_id,
                "asset_a": row.asset_a,
                "asset_b": row.asset_b,
                "side": row.side,
                "quantity_a": row.quantity_a,
                "quantity_b": row.quantity_b,
                "entry_price_a": row.entry_price_a,
                "entry_price_b": row.entry_price_b,
                "beta": row.beta,
                "entry_zscore": row.entry_zscore,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }

        manager = get_position_manager()
        position = manager.get_position(position_id)
        if not position:
            raise HTTPException(status_code=404, detail="Position not found")
        return position.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting position: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{position_id}")
async def delete_position(position_id: int, db: Session = Depends(get_db)):
    """Delete a position"""
    try:
        if db is not None:
            row = db.query(DbPosition).filter(DbPosition.id == position_id).first()
            if not row:
                raise HTTPException(status_code=404, detail="Position not found")
            db.delete(row)
            db.commit()
            return {"message": "Position deleted", "position_id": position_id}

        manager = get_position_manager()
        deleted = manager.delete_position(position_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Position not found")
        return {"message": "Position deleted", "position_id": position_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting position: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{position_id}/pnl")
async def get_position_pnl(
    position_id: int,
    current_price_a: float,
    current_price_b: float
    , db: Session = Depends(get_db)
):
    """Get current P&L for a position"""
    try:
        if db is not None:
            row = db.query(DbPosition).filter(DbPosition.id == position_id).first()
            if not row:
                raise HTTPException(status_code=404, detail="Position not found")

            if row.side == 'long':
                pnl_a = (current_price_a - row.entry_price_a) * row.quantity_a
                pnl_b = (row.entry_price_b - current_price_b) * row.quantity_b
            else:
                pnl_a = (row.entry_price_a - current_price_a) * row.quantity_a
                pnl_b = (current_price_b - row.entry_price_b) * row.quantity_b

            total_pnl = pnl_a + pnl_b
            return {
                "position_id": position_id,
                "pnl_a": pnl_a,
                "pnl_b": pnl_b,
                "total_pnl": total_pnl,
                "current_price_a": current_price_a,
                "current_price_b": current_price_b,
            }

        manager = get_position_manager()
        pnl = manager.calculate_pnl(position_id, current_price_a, current_price_b)
        if not pnl:
            raise HTTPException(status_code=404, detail="Position not found")
        return pnl
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating P&L: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


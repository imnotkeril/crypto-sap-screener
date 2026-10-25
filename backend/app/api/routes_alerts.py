"""
FastAPI routes for alerts management
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime

from app.database import get_db
from app.database import Alert as DbAlert
from app.modules.alerts.alert_manager import AlertManager
import logging

from app.api.validation import ensure_pair_exists
router = APIRouter()
logger = logging.getLogger(__name__)

# Global alert manager instance
_alert_manager: Optional[AlertManager] = None


def get_alert_manager() -> AlertManager:
    """Get or create global alert manager instance"""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager()
    return _alert_manager


@router.get("/")
async def get_alerts(pair_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Get all alerts, optionally filtered by pair_id"""
    try:
        if db is not None:
            q = db.query(DbAlert)
            if pair_id is not None:
                q = q.filter(DbAlert.pair_id == pair_id)
            rows = q.order_by(DbAlert.created_at.desc()).all()
            alerts = []
            for a in rows:
                alerts.append({
                    "alert_id": a.id,
                    "pair_id": a.pair_id,
                    "asset_a": a.asset_a,
                    "asset_b": a.asset_b,
                    "threshold_high": a.threshold_high,
                    "threshold_low": a.threshold_low,
                    "enabled": a.enabled == "true",
                    "last_triggered": a.last_triggered.isoformat() if a.last_triggered else None,
                    "trigger_count": a.trigger_count,
                })
            return {"alerts": alerts, "total": len(alerts)}

        # Fallback to in-memory
        manager = get_alert_manager()
        alerts = manager.get_alerts(pair_id=pair_id)
        return {'alerts': [alert.to_dict() for alert in alerts], 'total': len(alerts)}
    except Exception as e:
        logger.error(f"Error getting alerts: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/")
async def create_alert(
    pair_id: int,
    asset_a: str,
    asset_b: str,
    threshold_high: Optional[float] = None,
    threshold_low: Optional[float] = None
    , db: Session = Depends(get_db)
):
    """Create a new alert"""
    ensure_pair_exists(db, pair_id, asset_a, asset_b)
    try:
        if db is not None:
            # Default thresholds
            if threshold_high is None and threshold_low is None:
                threshold_high = 2.0
                threshold_low = -2.0
            row = DbAlert(
                pair_id=pair_id,
                asset_a=asset_a,
                asset_b=asset_b,
                threshold_high=threshold_high,
                threshold_low=threshold_low,
                enabled="true",
                created_at=datetime.utcnow(),
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return {
                "alert_id": row.id,
                "pair_id": row.pair_id,
                "asset_a": row.asset_a,
                "asset_b": row.asset_b,
                "threshold_high": row.threshold_high,
                "threshold_low": row.threshold_low,
                "enabled": row.enabled == "true",
                "last_triggered": None,
                "trigger_count": row.trigger_count,
            }

        manager = get_alert_manager()
        alert = manager.create_alert(pair_id=pair_id, asset_a=asset_a, asset_b=asset_b, threshold_high=threshold_high, threshold_low=threshold_low)
        return alert.to_dict()
    except Exception as e:
        logger.error(f"Error creating alert: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{alert_id}")
async def get_alert(alert_id: int, db: Session = Depends(get_db)):
    """Get alert by ID"""
    try:
        if db is not None:
            row = db.query(DbAlert).filter(DbAlert.id == alert_id).first()
            if not row:
                raise HTTPException(status_code=404, detail="Alert not found")
            return {
                "alert_id": row.id,
                "pair_id": row.pair_id,
                "asset_a": row.asset_a,
                "asset_b": row.asset_b,
                "threshold_high": row.threshold_high,
                "threshold_low": row.threshold_low,
                "enabled": row.enabled == "true",
                "last_triggered": row.last_triggered.isoformat() if row.last_triggered else None,
                "trigger_count": row.trigger_count,
            }

        manager = get_alert_manager()
        alert = manager.get_alert(alert_id)
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        return alert.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting alert: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/{alert_id}")
async def update_alert(
    alert_id: int,
    threshold_high: Optional[float] = None,
    threshold_low: Optional[float] = None,
    enabled: Optional[bool] = None
    , db: Session = Depends(get_db)
):
    """Update alert settings"""
    try:
        if db is not None:
            row = db.query(DbAlert).filter(DbAlert.id == alert_id).first()
            if not row:
                raise HTTPException(status_code=404, detail="Alert not found")
            if threshold_high is not None:
                row.threshold_high = threshold_high
            if threshold_low is not None:
                row.threshold_low = threshold_low
            if enabled is not None:
                row.enabled = "true" if enabled else "false"
            db.commit()
            db.refresh(row)
            return {
                "alert_id": row.id,
                "pair_id": row.pair_id,
                "asset_a": row.asset_a,
                "asset_b": row.asset_b,
                "threshold_high": row.threshold_high,
                "threshold_low": row.threshold_low,
                "enabled": row.enabled == "true",
                "last_triggered": row.last_triggered.isoformat() if row.last_triggered else None,
                "trigger_count": row.trigger_count,
            }

        manager = get_alert_manager()
        alert = manager.update_alert(alert_id=alert_id, threshold_high=threshold_high, threshold_low=threshold_low, enabled=enabled)
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        return alert.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating alert: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{alert_id}")
async def delete_alert(alert_id: int, db: Session = Depends(get_db)):
    """Delete an alert"""
    try:
        if db is not None:
            row = db.query(DbAlert).filter(DbAlert.id == alert_id).first()
            if not row:
                raise HTTPException(status_code=404, detail="Alert not found")
            db.delete(row)
            db.commit()
            return {"message": "Alert deleted", "alert_id": alert_id}

        manager = get_alert_manager()
        deleted = manager.delete_alert(alert_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Alert not found")
        return {"message": "Alert deleted", "alert_id": alert_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting alert: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/triggered/check")
async def check_triggered_alerts():
    """Check for triggered alerts based on current screening results"""
    try:
        from app.modules.screener.live_screener import get_live_screener
        
        manager = get_alert_manager()
        live_screener = get_live_screener()
        results = live_screener.get_results()
        
        # Check all pairs for triggered alerts
        triggered = manager.check_all_pairs(results)
        
        # Format response
        triggered_list = []
        for pair_id, alerts in triggered.items():
            for alert in alerts:
                triggered_list.append({
                    'alert_id': alert.alert_id,
                    'pair_id': pair_id,
                    'asset_a': alert.asset_a,
                    'asset_b': alert.asset_b,
                    'threshold_high': alert.threshold_high,
                    'threshold_low': alert.threshold_low,
                    'current_zscore': next((r.get('current_zscore', 0) for r in results if r.get('id') == pair_id), 0),
                    'last_triggered': alert.last_triggered.isoformat() if alert.last_triggered else None,
                    'trigger_count': alert.trigger_count
                })
        
        return {
            'triggered': triggered_list,
            'count': len(triggered_list)
        }
    except Exception as e:
        logger.error(f"Error checking triggered alerts: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


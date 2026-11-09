"""
Alert manager for monitoring Z-Score thresholds
"""
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import threading


ALERT_COOLDOWN_SECONDS = 900  # re-fire at most once per 15 min while the threshold stays crossed


def in_cooldown(last_triggered: Optional[datetime], now: Optional[datetime] = None) -> bool:
    now = now or datetime.utcnow()
    return last_triggered is not None and now - last_triggered < timedelta(seconds=ALERT_COOLDOWN_SECONDS)


class Alert:
    """Single alert configuration"""
    def __init__(
        self,
        alert_id: int,
        pair_id: int,
        asset_a: str,
        asset_b: str,
        threshold_high: Optional[float] = None,
        threshold_low: Optional[float] = None,
        enabled: bool = True
    ):
        self.alert_id = alert_id
        self.pair_id = pair_id
        self.asset_a = asset_a
        self.asset_b = asset_b
        self.threshold_high = threshold_high  # Alert when Z-Score >= this
        self.threshold_low = threshold_low  # Alert when Z-Score <= this
        self.enabled = enabled
        self.last_triggered: Optional[datetime] = None
        self.trigger_count = 0
    
    def to_dict(self) -> Dict:
        """Convert alert to dictionary"""
        return {
            'alert_id': self.alert_id,
            'pair_id': self.pair_id,
            'asset_a': self.asset_a,
            'asset_b': self.asset_b,
            'threshold_high': self.threshold_high,
            'threshold_low': self.threshold_low,
            'enabled': self.enabled,
            'last_triggered': self.last_triggered.isoformat() if self.last_triggered else None,
            'trigger_count': self.trigger_count
        }
    
    def check(self, zscore: float) -> bool:
        """
        Check if alert should trigger
        
        Args:
            zscore: Current Z-Score value
            
        Returns:
            True if alert should trigger
        """
        if not self.enabled or in_cooldown(self.last_triggered):
            return False
        
        triggered = False
        if self.threshold_high is not None and zscore >= self.threshold_high:
            triggered = True
        if self.threshold_low is not None and zscore <= self.threshold_low:
            triggered = True
        
        if triggered:
            self.last_triggered = datetime.utcnow()
            self.trigger_count += 1
        
        return triggered


class AlertManager:
    """Manages alerts for pairs trading"""
    
    def __init__(self):
        self._alerts: Dict[int, Alert] = {}  # alert_id -> Alert
        self._pair_alerts: Dict[int, List[int]] = {}  # pair_id -> [alert_ids]
        self._next_id = 1
        self._lock = threading.Lock()
    
    def create_alert(
        self,
        pair_id: int,
        asset_a: str,
        asset_b: str,
        threshold_high: Optional[float] = None,
        threshold_low: Optional[float] = None
    ) -> Alert:
        """
        Create a new alert
        
        Args:
            pair_id: Pair ID to monitor
            asset_a: First asset symbol
            asset_b: Second asset symbol
            threshold_high: Alert when Z-Score >= this (default: 2.0)
            threshold_low: Alert when Z-Score <= this (default: -2.0)
            
        Returns:
            Created Alert object
        """
        with self._lock:
            alert_id = self._next_id
            self._next_id += 1
            
            # Default thresholds
            if threshold_high is None and threshold_low is None:
                threshold_high = 2.0
                threshold_low = -2.0
            
            alert = Alert(
                alert_id=alert_id,
                pair_id=pair_id,
                asset_a=asset_a,
                asset_b=asset_b,
                threshold_high=threshold_high,
                threshold_low=threshold_low,
                enabled=True
            )
            
            self._alerts[alert_id] = alert
            
            # Track alerts by pair
            if pair_id not in self._pair_alerts:
                self._pair_alerts[pair_id] = []
            self._pair_alerts[pair_id].append(alert_id)
            
            return alert
    
    def get_alert(self, alert_id: int) -> Optional[Alert]:
        """Get alert by ID"""
        with self._lock:
            return self._alerts.get(alert_id)
    
    def get_alerts(self, pair_id: Optional[int] = None) -> List[Alert]:
        """
        Get all alerts, optionally filtered by pair_id
        
        Args:
            pair_id: Optional pair ID to filter by
            
        Returns:
            List of Alert objects
        """
        with self._lock:
            if pair_id is not None:
                alert_ids = self._pair_alerts.get(pair_id, [])
                return [self._alerts[aid] for aid in alert_ids if aid in self._alerts]
            return list(self._alerts.values())
    
    def delete_alert(self, alert_id: int) -> bool:
        """
        Delete an alert
        
        Args:
            alert_id: Alert ID to delete
            
        Returns:
            True if deleted, False if not found
        """
        with self._lock:
            if alert_id not in self._alerts:
                return False
            
            alert = self._alerts[alert_id]
            pair_id = alert.pair_id
            
            # Remove from pair tracking
            if pair_id in self._pair_alerts:
                self._pair_alerts[pair_id] = [aid for aid in self._pair_alerts[pair_id] if aid != alert_id]
                if not self._pair_alerts[pair_id]:
                    del self._pair_alerts[pair_id]
            
            del self._alerts[alert_id]
            return True
    
    def update_alert(
        self,
        alert_id: int,
        threshold_high: Optional[float] = None,
        threshold_low: Optional[float] = None,
        enabled: Optional[bool] = None
    ) -> Optional[Alert]:
        """
        Update alert settings
        
        Args:
            alert_id: Alert ID to update
            threshold_high: New high threshold (None to keep current)
            threshold_low: New low threshold (None to keep current)
            enabled: New enabled status (None to keep current)
            
        Returns:
            Updated Alert or None if not found
        """
        with self._lock:
            if alert_id not in self._alerts:
                return None
            
            alert = self._alerts[alert_id]
            
            if threshold_high is not None:
                alert.threshold_high = threshold_high
            if threshold_low is not None:
                alert.threshold_low = threshold_low
            if enabled is not None:
                alert.enabled = enabled
            
            return alert
    
    def check_pair(self, pair_id: int, zscore: float) -> List[Alert]:
        """
        Check all alerts for a pair
        
        Args:
            pair_id: Pair ID to check
            zscore: Current Z-Score value
            
        Returns:
            List of triggered alerts
        """
        triggered = []
        with self._lock:
            alert_ids = self._pair_alerts.get(pair_id, [])
            for alert_id in alert_ids:
                if alert_id in self._alerts:
                    alert = self._alerts[alert_id]
                    if alert.check(zscore):
                        triggered.append(alert)
        return triggered
    
    def check_all_pairs(self, pairs_data: List[Dict]) -> Dict[int, List[Alert]]:
        """
        Check alerts for all pairs
        
        Args:
            pairs_data: List of pair dictionaries with 'id' and 'current_zscore'
            
        Returns:
            Dictionary mapping pair_id to list of triggered alerts
        """
        results = {}
        for pair in pairs_data:
            pair_id = pair.get('id')
            zscore = pair.get('current_zscore', 0.0) or 0.0
            if pair_id:
                triggered = self.check_pair(pair_id, zscore)
                if triggered:
                    results[pair_id] = triggered
        return results



    def check_assets(self, asset_a: str, asset_b: str, zscore: float) -> List[Alert]:
        """Check alerts keyed by the canonical (asset_a, asset_b) pair, not by scan rank."""
        triggered = []
        with self._lock:
            for alert in self._alerts.values():
                if alert.asset_a == asset_a and alert.asset_b == asset_b and alert.check(zscore):
                    triggered.append(alert)
        return triggered


def threshold_hit(zscore: float, high: Optional[float], low: Optional[float]) -> bool:
    """True when zscore crosses either (inclusive) threshold."""
    return (high is not None and zscore >= high) or (low is not None and zscore <= low)

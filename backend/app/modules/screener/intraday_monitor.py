"""
Intraday spread monitor.

The daily screener finds cointegrated pairs and fits a static hedge ratio
(alpha, beta) plus the historical mean/std of the spread. This monitor takes
those already-fitted parameters for the top-ranked pairs and re-evaluates the
spread z-score against *live* prices, polled at a much higher frequency than
the daily screening cycle. This surfaces intraday divergences that would
otherwise only be visible once the next daily screen runs.

In a serverless deployment there is no long-lived background loop, so the
snapshot is recomputed synchronously on each request. History for sparklines
is persisted to the database (table `intraday_snapshots`).
"""
import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from app.modules.screener.data_loader import DataLoader
from app.modules.screener.kalman import KalmanHedge
from app.modules.screener.live_screener import get_live_screener
from app.database import SessionLocal, IntradaySnapshot
from app.config import settings

logger = logging.getLogger(__name__)

HISTORY_LEN = 240  # samples kept per pair for sparkline/history

# Minimum aligned intraday candles before the Kalman fit is trustworthy.
MIN_KALMAN_BARS = 60


def _pair_key(asset_a: str, asset_b: str) -> str:
    return f"{asset_a}_{asset_b}"


class IntradayMonitor:
    """Re-prices the top daily pairs on demand and tracks live z-scores."""

    def __init__(self):
        self.interval = settings.INTRADAY_MONITOR_INTERVAL
        self.top_n = settings.INTRADAY_TOP_PAIRS
        self.alert_threshold = settings.INTRADAY_ZSCORE_ALERT_THRESHOLD

        self.kalman_timeframe = settings.INTRADAY_KALMAN_TIMEFRAME
        self.kalman_days = settings.INTRADAY_KALMAN_LOOKBACK_DAYS
        self.kalman = KalmanHedge(
            delta=settings.INTRADAY_KALMAN_DELTA,
            r=settings.INTRADAY_KALMAN_R,
        )

        self.snapshot: List[Dict] = []
        self.last_update: Optional[datetime] = None
        self.last_error: Optional[str] = None
        self.skipped_pairs = 0
        self._lock = threading.Lock()

        self.data_loader = DataLoader()

    @property
    def is_running(self) -> bool:
        # Kept for API compatibility - snapshots are computed on demand.
        return True

    def start(self):
        # No-op: snapshots are computed synchronously per request.
        pass

    def stop(self):
        pass

    def get_snapshot(self) -> Dict:
        with self._lock:
            fresh = (
                self.last_update is not None
                and (datetime.utcnow() - self.last_update).total_seconds() < self.interval
            )
            if not fresh:
                try:
                    self._update()
                    self.last_error = None
                except Exception as e:
                    logger.error(f"Intraday monitor error: {e}")
                    self.last_error = "Live update failed; see server logs"

        return {
            'pairs': [p.copy() for p in self.snapshot],
            'last_update': self.last_update.isoformat() if self.last_update else None,
            'is_running': True,
            'interval_seconds': self.interval,
            'alert_threshold': self.alert_threshold,
            'last_error': self.last_error,
            'skipped_pairs': self.skipped_pairs,
        }

    def get_history(self, asset_a: str, asset_b: str) -> List[Dict]:
        if SessionLocal is None:
            return []
        db = SessionLocal()
        try:
            a1, b1 = (asset_a, asset_b) if asset_a <= asset_b else (asset_b, asset_a)
            cutoff = datetime.utcnow() - timedelta(hours=2)
            rows = (
                db.query(IntradaySnapshot)
                .filter(
                    IntradaySnapshot.asset_a == a1,
                    IntradaySnapshot.asset_b == b1,
                    IntradaySnapshot.created_at >= cutoff,
                )
                .order_by(IntradaySnapshot.created_at.asc())
                .limit(HISTORY_LEN)
                .all()
            )
            return [{'t': r.created_at.isoformat(), 'z': r.zscore} for r in rows]
        except Exception as e:
            logger.warning(f"Could not load intraday history: {e}")
            return []
        finally:
            try:
                db.close()
            except Exception:
                pass

    def _recent_prices(self, asset: str, fetched: Dict[str, pd.Series]) -> pd.Series:
        """Fresh intraday closes (bypasses the screener's long-lived price cache)."""
        if asset not in fetched:
            df = self.data_loader.fetch_ohlcv(
                asset, days=self.kalman_days, timeframe=self.kalman_timeframe
            )
            fetched[asset] = df['close'] if df is not None and not df.empty else pd.Series(dtype=float)
        return fetched[asset]

    def _update(self):
        live = get_live_screener()
        daily_results = live.get_results()
        if not daily_results:
            return

        candidates = sorted(
            daily_results,
            key=lambda r: r.get('composite_score', 0) or 0,
            reverse=True
        )[:self.top_n]

        now = datetime.utcnow()
        snapshot = []
        db_rows = []
        fetched: Dict[str, pd.Series] = {}
        skipped = 0

        for r in candidates:
            a, b = r['asset_a'], r['asset_b']

            # Re-fit the hedge ratio on recent intraday candles rather than
            # reusing the (possibly stale) daily fit. The last candle close is
            # effectively the live price (ccxt returns the forming candle).
            try:
                price_a = self._recent_prices(a, fetched)
                price_b = self._recent_prices(b, fetched)
            except Exception as e:
                logger.warning(f"Intraday monitor: candle fetch failed for {a}/{b}: {e}")
                skipped += 1
                continue

            aligned = pd.DataFrame({'a': price_a, 'b': price_b}).dropna()
            if len(aligned) < MIN_KALMAN_BARS:
                skipped += 1
                continue

            kf = self.kalman.run(aligned['a'], aligned['b'])
            if kf.empty:
                continue

            last = kf.iloc[-1]
            beta = float(last['beta'])
            spread_now = float(last['spread'])
            zscore = float(last['zscore'])
            if not np.isfinite(zscore) or not np.isfinite(beta):
                continue

            pa = float(aligned['a'].iloc[-1])
            pb = float(aligned['b'].iloc[-1])
            daily_zscore = float(r.get('current_zscore', 0.0) or 0.0)

            entry = {
                'pair_id': r.get('id'),
                'asset_a': a,
                'asset_b': b,
                'price_a': pa,
                'price_b': pb,
                'beta': beta,
                'spread': spread_now,
                'zscore': zscore,
                'daily_zscore': daily_zscore,
                'zscore_delta': zscore - daily_zscore,
                'is_unusual': bool(abs(zscore) >= self.alert_threshold),
                'updated_at': now.isoformat(),
            }
            snapshot.append(entry)

            a1, b1 = (a, b) if a <= b else (b, a)
            db_rows.append(IntradaySnapshot(
                asset_a=a1,
                asset_b=b1,
                price_a=pa,
                price_b=pb,
                beta=beta,
                spread=spread_now,
                zscore=zscore,
                created_at=now,
            ))

        snapshot.sort(key=lambda x: abs(x['zscore']), reverse=True)
        self.snapshot = snapshot
        self.skipped_pairs = skipped
        self.last_update = now

        self._persist_snapshots(db_rows, now)

    def _persist_snapshots(self, db_rows, now: datetime):
        if SessionLocal is None or not db_rows:
            return
        db = SessionLocal()
        try:
            for row in db_rows:
                db.add(row)
            db.commit()

            # Prune old rows so the table doesn't grow unbounded.
            cutoff = now - timedelta(hours=6)
            db.query(IntradaySnapshot).filter(IntradaySnapshot.created_at < cutoff).delete()
            db.commit()
        except Exception as e:
            logger.warning(f"Could not persist intraday snapshots: {e}")
        finally:
            try:
                db.close()
            except Exception:
                pass


_intraday_monitor: Optional[IntradayMonitor] = None


def get_intraday_monitor() -> IntradayMonitor:
    global _intraday_monitor
    if _intraday_monitor is None:
        _intraday_monitor = IntradayMonitor()
    return _intraday_monitor

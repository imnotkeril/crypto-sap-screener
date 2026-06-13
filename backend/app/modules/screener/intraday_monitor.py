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
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from app.modules.screener.data_loader import DataLoader
from app.modules.screener.live_screener import get_live_screener
from app.database import SessionLocal, IntradaySnapshot
from app.config import settings

logger = logging.getLogger(__name__)

HISTORY_LEN = 240  # samples kept per pair for sparkline/history


def _pair_key(asset_a: str, asset_b: str) -> str:
    return f"{asset_a}_{asset_b}"


class IntradayMonitor:
    """Re-prices the top daily pairs on demand and tracks live z-scores."""

    def __init__(self):
        self.interval = settings.INTRADAY_MONITOR_INTERVAL
        self.top_n = settings.INTRADAY_TOP_PAIRS
        self.alert_threshold = settings.INTRADAY_ZSCORE_ALERT_THRESHOLD

        self.snapshot: List[Dict] = []
        self.last_update: Optional[datetime] = None
        self.last_error: Optional[str] = None

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
        try:
            self._update()
            self.last_error = None
        except Exception as e:
            logger.error(f"Intraday monitor error: {e}")
            self.last_error = str(e)

        return {
            'pairs': [p.copy() for p in self.snapshot],
            'last_update': self.last_update.isoformat() if self.last_update else None,
            'is_running': True,
            'interval_seconds': self.interval,
            'alert_threshold': self.alert_threshold,
            'last_error': self.last_error,
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

        symbols = set()
        for r in candidates:
            symbols.add(r['asset_a'])
            symbols.add(r['asset_b'])

        prices = self._fetch_prices(symbols)
        if not prices:
            return

        now = datetime.utcnow()
        snapshot = []
        db_rows = []

        for r in candidates:
            a, b = r['asset_a'], r['asset_b']
            pa, pb = prices.get(a), prices.get(b)
            if pa is None or pb is None:
                continue

            alpha = r.get('alpha', 0.0) or 0.0
            beta = r['beta']
            mean_spread = r.get('mean_spread', 0.0) or 0.0
            std = r.get('spread_std') or 1.0

            spread_now = pa - (alpha + beta * pb)
            zscore = (spread_now - mean_spread) / std if std else 0.0
            daily_zscore = r.get('current_zscore', 0.0) or 0.0

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
                'is_unusual': abs(zscore) >= self.alert_threshold,
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

    def _fetch_prices(self, symbols) -> Dict[str, float]:
        """Fetch last traded prices for a set of base symbols via Binance tickers."""
        exchange = self.data_loader.exchange
        prices: Dict[str, float] = {}
        try:
            market_symbols = [f"{s}/USDT" for s in symbols]
            tickers = exchange.fetch_tickers(market_symbols)
            for sym, ticker in tickers.items():
                base = sym.split('/')[0]
                last = ticker.get('last') or ticker.get('close')
                if last:
                    prices[base] = float(last)
        except Exception as e:
            logger.warning(f"Intraday monitor: failed to fetch live prices: {e}")
        return prices


_intraday_monitor: Optional[IntradayMonitor] = None


def get_intraday_monitor() -> IntradayMonitor:
    global _intraday_monitor
    if _intraday_monitor is None:
        _intraday_monitor = IntradayMonitor()
    return _intraday_monitor

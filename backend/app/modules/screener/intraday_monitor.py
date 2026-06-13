"""
Intraday spread monitor.

The daily screener finds cointegrated pairs and fits a static hedge ratio
(alpha, beta) plus the historical mean/std of the spread. This monitor takes
those already-fitted parameters for the top-ranked pairs and re-evaluates the
spread z-score against *live* prices, polled at a much higher frequency than
the daily screening cycle. This surfaces intraday divergences that would
otherwise only be visible once the next daily screen runs.
"""
import threading
import time
import logging
from collections import deque
from datetime import datetime
from typing import Dict, List, Optional

from app.modules.screener.data_loader import DataLoader
from app.modules.screener.live_screener import get_live_screener
from app.config import settings

logger = logging.getLogger(__name__)

HISTORY_LEN = 240  # samples kept per pair for sparkline/history


def _pair_key(asset_a: str, asset_b: str) -> str:
    return f"{asset_a}_{asset_b}"


class IntradayMonitor:
    """Continuously re-prices the top daily pairs and tracks live z-scores."""

    def __init__(self):
        self.is_running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        self.interval = settings.INTRADAY_MONITOR_INTERVAL
        self.top_n = settings.INTRADAY_TOP_PAIRS
        self.alert_threshold = settings.INTRADAY_ZSCORE_ALERT_THRESHOLD

        self.snapshot: List[Dict] = []
        self.history: Dict[str, deque] = {}
        self.last_update: Optional[datetime] = None
        self.last_error: Optional[str] = None

        self.data_loader = DataLoader()

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("Intraday monitor started")

    def stop(self):
        self.is_running = False
        if self._thread:
            self._thread.join(timeout=5)

    def get_snapshot(self) -> Dict:
        with self._lock:
            return {
                'pairs': [p.copy() for p in self.snapshot],
                'last_update': self.last_update.isoformat() if self.last_update else None,
                'is_running': self.is_running,
                'interval_seconds': self.interval,
                'alert_threshold': self.alert_threshold,
                'last_error': self.last_error,
            }

    def get_history(self, asset_a: str, asset_b: str) -> List[Dict]:
        key = _pair_key(asset_a, asset_b)
        alt_key = _pair_key(asset_b, asset_a)
        with self._lock:
            if key in self.history:
                return list(self.history[key])
            if alt_key in self.history:
                return list(self.history[alt_key])
            return []

    def _run_loop(self):
        while self.is_running:
            try:
                self._update()
                self.last_error = None
            except Exception as e:
                logger.error(f"Intraday monitor error: {e}")
                self.last_error = str(e)
            time.sleep(self.interval)

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

        with self._lock:
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

                key = _pair_key(a, b)
                hist = self.history.setdefault(key, deque(maxlen=HISTORY_LEN))
                hist.append({'t': now.isoformat(), 'z': zscore})

            snapshot.sort(key=lambda x: abs(x['zscore']), reverse=True)
            self.snapshot = snapshot
            self.last_update = now

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

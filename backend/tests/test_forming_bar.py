"""R-01: the still-forming candle must never reach the z-score."""
from app.modules.screener.data_loader import DataLoader, TIMEFRAME_MS


class FakeExchange:
    def __init__(self, now_ms, candles):
        self._now = now_ms
        self._candles = candles

    def milliseconds(self):
        return self._now

    def fetch_ohlcv(self, symbol, timeframe, since=None, limit=None):
        return self._candles


def _loader(now_ms, candles):
    dl = object.__new__(DataLoader)
    dl.exchange = FakeExchange(now_ms, candles)
    return dl


def test_fetch_ohlcv_drops_forming_candle():
    day = TIMEFRAME_MS['1d']
    now = 10 * day + day // 2  # halfway through day 10
    candles = [[i * day, 1, 1, 1, float(i), 1] for i in range(5, 11)]  # day 10 is forming
    df = _loader(now, candles).fetch_ohlcv('BTC', days=6, timeframe='1d')
    assert len(df) == 5
    assert df['close'].iloc[-1] == 9.0


def test_fetch_ohlcv_keeps_closed_candle_at_boundary():
    h = TIMEFRAME_MS['1h']
    now = 10 * h
    candles = [[i * h, 1, 1, 1, float(i), 1] for i in range(5, 10)]
    df = _loader(now, candles).fetch_ohlcv('BTC', days=1, timeframe='1h')
    assert df['close'].iloc[-1] == 9.0

"""
Indicator computation (___DataLayer.md section 9).

Recomputed from the rolling candle window each time a candle closes -
simpler and less error-prone than maintaining incremental state, and cheap
enough at the window sizes used here (<= 500 candles).

| Indicator  | Params                  |
|------------|-------------------------|
| EMA        | periods: 9, 21, 50, 200 |
| RSI        | period: 14              |
| VWAP       | session-based (per UTC day) |
| Bollinger  | period: 20, std: 2      |
| ATR        | period: 14              |
| Volume SMA | period: 20              |
"""
from typing import List

import pandas as pd

EMA_PERIODS = [9, 21, 50, 200]
RSI_PERIOD = 14
BOLLINGER_PERIOD = 20
BOLLINGER_STD = 2
ATR_PERIOD = 14
VOLUME_SMA_PERIOD = 20


def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))


def _atr(df: pd.DataFrame, period: int) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def _vwap(df: pd.DataFrame) -> pd.Series:
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    session = df["timestamp"].dt.floor("D")
    cum_pv = (typical_price * df["volume"]).groupby(session).cumsum()
    cum_vol = df["volume"].groupby(session).cumsum()
    return cum_pv / cum_vol.replace(0, pd.NA)


def compute_indicators(candles: List[dict]) -> dict:
    """Compute the latest value of each indicator from a list of candle dicts
    (oldest first), as produced by RedisStore.get_latest_candles / Candle.to_dict.

    Returns an empty dict if there isn't enough history yet.
    """
    if len(candles) < 2:
        return {}

    df = pd.DataFrame(candles)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)

    result = {}

    for period in EMA_PERIODS:
        ema = df["close"].ewm(span=period, min_periods=period, adjust=False).mean()
        if not ema.empty and pd.notna(ema.iloc[-1]):
            result[f"ema_{period}"] = float(ema.iloc[-1])

    rsi = _rsi(df["close"], RSI_PERIOD)
    if not rsi.empty and pd.notna(rsi.iloc[-1]):
        result["rsi_14"] = float(rsi.iloc[-1])

    if len(df) >= BOLLINGER_PERIOD:
        window = df["close"].rolling(BOLLINGER_PERIOD)
        mid = window.mean()
        std = window.std()
        if pd.notna(mid.iloc[-1]) and pd.notna(std.iloc[-1]):
            result["bollinger_mid"] = float(mid.iloc[-1])
            result["bollinger_upper"] = float(mid.iloc[-1] + BOLLINGER_STD * std.iloc[-1])
            result["bollinger_lower"] = float(mid.iloc[-1] - BOLLINGER_STD * std.iloc[-1])

    atr = _atr(df, ATR_PERIOD)
    if not atr.empty and pd.notna(atr.iloc[-1]):
        result["atr_14"] = float(atr.iloc[-1])

    if len(df) >= VOLUME_SMA_PERIOD:
        vol_sma = df["volume"].rolling(VOLUME_SMA_PERIOD).mean().iloc[-1]
        if pd.notna(vol_sma):
            result["volume_sma_20"] = float(vol_sma)

    vwap = _vwap(df)
    if not vwap.empty and pd.notna(vwap.iloc[-1]):
        result["vwap"] = float(vwap.iloc[-1])

    return result

"""
Validation of normalized Candle/Ticker objects.

Bad data points (negative volume, zero/negative prices, inconsistent OHLC)
are dropped and logged per ___DataLayer.md section 13.
"""
import logging

from app.data_layer.core.exceptions import ValidationError
from app.data_layer.core.models import Candle, Ticker

logger = logging.getLogger(__name__)


def validate_candle(candle: Candle) -> None:
    """Raise ValidationError if the candle contains bad data."""
    if candle.open <= 0 or candle.high <= 0 or candle.low <= 0 or candle.close <= 0:
        raise ValidationError(f"Non-positive price in candle: {candle}")

    if candle.volume < 0:
        raise ValidationError(f"Negative volume in candle: {candle}")

    if candle.high < candle.low:
        raise ValidationError(f"high < low in candle: {candle}")

    if not (candle.low <= candle.open <= candle.high):
        raise ValidationError(f"open outside [low, high] in candle: {candle}")

    if not (candle.low <= candle.close <= candle.high):
        raise ValidationError(f"close outside [low, high] in candle: {candle}")


def validate_ticker(ticker: Ticker) -> None:
    """Raise ValidationError if the ticker contains bad data."""
    if ticker.last <= 0:
        raise ValidationError(f"Non-positive last price in ticker: {ticker}")

    if ticker.bid < 0 or ticker.ask < 0:
        raise ValidationError(f"Negative bid/ask in ticker: {ticker}")

    if ticker.volume_24h < 0:
        raise ValidationError(f"Negative volume_24h in ticker: {ticker}")


def is_valid(obj) -> bool:
    """Return True if obj passes validation, logging and returning False otherwise."""
    try:
        if isinstance(obj, Candle):
            validate_candle(obj)
        elif isinstance(obj, Ticker):
            validate_ticker(obj)
        else:
            raise ValidationError(f"Unknown object type for validation: {type(obj)}")
        return True
    except ValidationError as e:
        logger.warning(f"Dropping invalid data point: {e}")
        return False

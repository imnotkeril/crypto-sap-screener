"""
Symbol normalization: exchange-native <-> unified "BASE/QUOTE" form.

Binance uses concatenated symbols (BTCUSDT). To split them back into
BASE/QUOTE we need to know the quote asset, since both the base and quote
can vary in length (e.g. BTCUSDT vs 1000SHIBUSDT).
"""

# Ordered by specificity - longer/rarer quote assets first so e.g. "BUSD"
# isn't mistaken for "USD".
_KNOWN_QUOTES = [
    "USDT", "USDC", "BUSD", "FDUSD", "TUSD", "DAI",
    "BTC", "ETH", "BNB", "EUR", "TRY", "USD",
]


def to_unified(exchange_symbol: str) -> str:
    """Convert an exchange-native symbol (e.g. BTCUSDT) to unified BASE/QUOTE (BTC/USDT)."""
    if "/" in exchange_symbol:
        return exchange_symbol.upper()

    symbol = exchange_symbol.upper()
    for quote in _KNOWN_QUOTES:
        if symbol.endswith(quote) and len(symbol) > len(quote):
            base = symbol[: -len(quote)]
            return f"{base}/{quote}"

    raise ValueError(f"Could not determine quote asset for symbol: {exchange_symbol}")


def to_exchange(unified_symbol: str) -> str:
    """Convert unified BASE/QUOTE (BTC/USDT) to exchange-native (BTCUSDT)."""
    return unified_symbol.upper().replace("/", "")

"""
Market Data Layer

Independent module that connects to exchanges (currently Binance) via
WebSocket and REST, normalizes/validates the data, stores real-time state in
Redis and history in Postgres, and serves it to consumers (screener,
terminal, backtester) via a query API and pub/sub.

Scope (v1): Binance only, candles (OHLCV) + ticker.
See ___DataLayer.md for the full target spec; this is a focused subset of it.
"""

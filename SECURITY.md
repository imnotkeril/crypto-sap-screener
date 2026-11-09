# Security Policy

## Scope

This is a research tool for crypto pairs screening. It never places orders and needs no exchange keys (public market data only). The optional `BINANCE_API_KEY` / `BINANCE_API_SECRET` variables, if you set them, must never have trading or withdrawal permissions.

## Reporting a vulnerability

Please do not open a public issue for security problems. Use GitHub's private reporting: **Security -> Report a vulnerability** on https://github.com/imnotkeril/crypto-sap-screener/security/advisories/new.

Include the affected file or endpoint, steps to reproduce and the impact. You can expect an acknowledgement within a few days. This is a personal project maintained on a best-effort basis.

## Supported versions

Only the latest commit on `main` is supported.

## Hardening notes

- Set `API_KEY` and `REQUIRE_AUTH=true` for any deployment that is reachable beyond localhost; set `CORS_ORIGINS` to your frontend origin.
- Never commit `.env` files. Only `.env.example` (names, no values) is tracked.
- The frontend Docker image injects `API_KEY` into proxied requests, so keep it bound to localhost or behind authentication.
- Details of the threat model and past review findings: [`docs/SECURITY.md`](docs/SECURITY.md).

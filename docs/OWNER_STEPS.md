# Owner steps (what only the owner can do)

1. Merge PR #11 (chore/audit -> main) on GitHub after a look at the diff.
2. Pick a host. Default: one small VPS (e.g. Hetzner CX22) running `docker compose up -d`. Needs: server, domain, DNS A record.
3. Create `.env` on the host from `.env.example` with API_KEY, CRON_SECRET, REDIS_PASSWORD, POSTGRES_PASSWORD (long random strings; never in chat/git).
4. TLS: Caddy or nginx + Let's Encrypt in front of the frontend container; set CORS_ORIGINS to the real origin.
5. Auth in front of the UI (the proxy injects API_KEY): SSO/VPN/auth_basic, or keep the allowlist and use the app only over VPN/localhost.
6. Alerts channel: in-app only, or Telegram (needs a bot token from @BotFather + your chat id).
7. LICENSE: choose (MIT / none).
8. History purge of backend/data/stat_arb.db (rewrites git history, force-push): yes/no.
9. pip SSL chain: allow `--trusted-host` or fix the corporate/self-signed certificate.

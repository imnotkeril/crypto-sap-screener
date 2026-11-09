"""R-06: failed cold-start scans must not be retried on every /status poll."""
from app.api import routes
from app.config import settings
from app.modules.screener import live_screener as ls


def test_cold_start_scan_backoff(client, auth, monkeypatch):
    scr = ls.get_live_screener()
    calls = []
    monkeypatch.setattr(scr, "_run_screening", lambda: calls.append(1))  # "fails": never sets a session
    monkeypatch.setattr(scr, "get_last_session", lambda: None)
    monkeypatch.setattr(settings, "AUTO_SCREEN_ON_COLD_START", True)
    monkeypatch.setattr(routes, "_last_cold_start_attempt", None)
    for _ in range(5):
        assert client.get("/api/v1/screener/status", headers=auth).status_code == 200
    assert len(calls) == 1


def test_cold_start_allowed_after_backoff(monkeypatch):
    monkeypatch.setattr(routes, "_last_cold_start_attempt", 100.0)
    assert not routes._cold_start_allowed(now=100.0 + routes.COLD_START_BACKOFF_SECONDS - 1)
    assert routes._cold_start_allowed(now=100.0 + routes.COLD_START_BACKOFF_SECONDS)

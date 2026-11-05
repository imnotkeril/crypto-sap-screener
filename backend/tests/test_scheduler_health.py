"""B2 scheduler due-logic and B3 /health scan freshness."""
from datetime import datetime, timedelta

from app.config import settings
from app.modules.screener import live_screener as ls


def test_scheduler_due_logic():
    s = ls.LiveScreener.__new__(ls.LiveScreener)
    s.screening_interval = 1800
    now = datetime(2026, 1, 1, 12, 0)
    s.last_screening_time = None
    s._last_scheduled_attempt = None
    assert s._scheduler_due(now)
    s._last_scheduled_attempt = now - timedelta(seconds=100)       # failed attempt: back off
    assert not s._scheduler_due(now)
    s._last_scheduled_attempt = now - timedelta(seconds=1800)
    assert s._scheduler_due(now)
    s.last_screening_time = now - timedelta(seconds=10)            # fresh data
    assert not s._scheduler_due(now)


def test_health_reports_scan_age_and_goes_503_when_stale(client, monkeypatch):
    scr = ls.get_live_screener()
    monkeypatch.setattr(settings, "SCAN_SCHEDULER_ENABLED", True)
    monkeypatch.setattr(settings, "SCAN_INTERVAL_SECONDS", 1800)
    monkeypatch.setattr(scr, "last_screening_time", datetime.utcnow() - timedelta(seconds=60))
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["last_scan_age_seconds"] < 120
    monkeypatch.setattr(scr, "last_screening_time", datetime.utcnow() - timedelta(seconds=3 * 1800))
    r = client.get("/health")
    assert r.status_code == 503 and r.json()["status"] == "stale"


def test_health_ok_when_scheduler_disabled_even_if_old(client, monkeypatch):
    scr = ls.get_live_screener()
    monkeypatch.setattr(settings, "SCAN_SCHEDULER_ENABLED", False)
    monkeypatch.setattr(scr, "last_screening_time", datetime.utcnow() - timedelta(days=3))
    assert client.get("/health").status_code == 200

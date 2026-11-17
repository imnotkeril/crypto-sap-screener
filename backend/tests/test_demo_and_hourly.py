import pytest

from app.config import settings
from app.modules.screener import snapshot_store
from app.modules.screener.screener import adf_score_for


def test_adf_score_follows_configured_threshold():
    # same p-value scores higher when the allowed threshold is looser
    assert adf_score_for(0.05, 0.10) == pytest.approx(0.5)
    assert adf_score_for(0.05, 0.20) == pytest.approx(0.75)
    assert adf_score_for(0.30, 0.10) == 0.0
    assert adf_score_for(0.0, 0.10) == 1.0
    assert adf_score_for(0.05, 0.0) == pytest.approx(0.5)  # falls back to 0.1


def test_demo_mode_blocks_manual_runs(client, auth, monkeypatch):
    monkeypatch.setattr(settings, "DEMO_MODE", True)
    assert client.post("/api/v1/screener/run", json={"timeframe": "1d"}, headers=auth).status_code == 403
    assert client.post("/api/v1/screener/run-live", headers=auth).status_code == 403
    assert client.get("/api/v1/screener/status", headers=auth).json()["demo_mode"] is True


def test_status_reports_demo_flag_off_by_default(client, auth, monkeypatch):
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    assert client.get("/api/v1/screener/status", headers=auth).json()["demo_mode"] is False


def test_results_timeframe_serves_snapshot(client, auth, monkeypatch):
    snap = {"results": [{
        "asset_a": "ETH", "asset_b": "SOL", "correlation": 0.9, "adf_pvalue": 0.02,
        "adf_statistic": -3.9, "beta": 20.0, "spread_std": 4.0, "half_life": 5.0,
        "screening_date": "2026-11-17T08:00:00", "timeframe": "1h",
    }]}
    monkeypatch.setattr(snapshot_store, "load_snapshot", lambda name="snapshot": snap if name == "snapshot-1h" else None)
    r = client.get("/api/v1/screener/results", params={"timeframe": "1h"}, headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1 and body["results"][0]["asset_a"] == "ETH"


def test_results_rejects_unknown_timeframe(client, auth):
    assert client.get("/api/v1/screener/results", params={"timeframe": "7m"}, headers=auth).status_code == 400


def test_cron_rejects_unknown_timeframe(client):
    assert client.get("/api/v1/screener/cron/run", params={"timeframe": "7m"}, headers={"Authorization": "Bearer cron-secret"}).status_code == 400

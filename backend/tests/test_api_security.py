from app.database import SessionLocal, PairsScreeningResult
from datetime import datetime


def test_health_is_open(client):
    assert client.get("/health").status_code == 200


def test_api_requires_key(client, auth):
    assert client.get("/api/v1/screener/status").status_code == 401
    assert client.get("/api/v1/screener/status", headers={"X-API-Key": "bad"}).status_code == 401
    assert client.get("/api/v1/screener/status", headers=auth).status_code == 200


def test_debug_endpoint_removed(client, auth):
    assert client.get("/api/v1/screener/debug/db", headers=auth).status_code in (404, 422)


def test_cors_restricted(client):
    ok = client.options("/api/v1/screener/status", headers={
        "Origin": "http://allowed.example", "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "http://allowed.example"
    bad = client.options("/api/v1/screener/status", headers={
        "Origin": "http://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in bad.headers


def test_cron_requires_secret(client, auth, monkeypatch):
    from app.modules.screener import live_screener as ls
    calls = []
    monkeypatch.setattr(ls.get_live_screener(), "_run_screening", lambda: calls.append(1))
    assert client.get("/api/v1/screener/cron/run").status_code == 401
    assert client.get("/api/v1/screener/cron/run",
                      headers={"Authorization": "Bearer wrong"}).status_code == 401
    r = client.get("/api/v1/screener/cron/run", headers={"Authorization": "Bearer cron-secret"})
    assert r.status_code == 200 and calls == [1]


def _seed_pair():
    db = SessionLocal()
    try:
        row = db.query(PairsScreeningResult).first()
        if row is None:
            from app.database import ScreeningSession
            s = ScreeningSession(started_at=datetime.utcnow(), status="completed")
            db.add(s); db.commit(); db.refresh(s)
            row = PairsScreeningResult(session_id=s.id, asset_a="BTC", asset_b="ETH",
                                       correlation=0.9, adf_pvalue=0.01, adf_statistic=-3.0,
                                       beta=1.0, alpha=0.0, spread_std=1.0,
                                       screening_date=datetime.utcnow(), lookback_days=365)
            db.add(row); db.commit(); db.refresh(row)
        return row.id, row.asset_a, row.asset_b
    finally:
        db.close()


def test_alert_pair_validation(client, auth):
    pid, a, b = _seed_pair()
    bad = client.post("/api/v1/alerts/", params={"pair_id": 999999, "asset_a": a, "asset_b": b}, headers=auth)
    assert bad.status_code == 404
    mismatch = client.post("/api/v1/alerts/", params={"pair_id": pid, "asset_a": "XXX", "asset_b": b}, headers=auth)
    assert mismatch.status_code == 422
    ok = client.post("/api/v1/alerts/", params={"pair_id": pid, "asset_a": a, "asset_b": b}, headers=auth)
    assert ok.status_code == 200
    assert client.delete(f"/api/v1/alerts/{ok.json()['alert_id']}", headers=auth).status_code == 200


def test_position_pair_validation(client, auth):
    pid, a, b = _seed_pair()
    body = dict(pair_id=999999, asset_a=a, asset_b=b, side="long", quantity_a=1, quantity_b=1,
                entry_price_a=1, entry_price_b=1, beta=1, entry_zscore=2)
    assert client.post("/api/v1/positions/", json=body, headers=auth).status_code == 404
    body["pair_id"] = pid
    r = client.post("/api/v1/positions/", json=body, headers=auth)
    assert r.status_code == 200
    assert client.delete(f"/api/v1/positions/{r.json()['position_id']}", headers=auth).status_code == 200

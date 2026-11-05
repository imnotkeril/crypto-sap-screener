"""Alert/position managers + API CRUD, auth matrix, exports, live-screener overlap.

xfail(strict=True) tests document OPEN BUGS (none left as of 2026-11-05; see docs/QA.md); they flip to XPASS->fail once fixed,
forcing the marker to be removed.
"""
import io
import threading

import pandas as pd
import pytest

from app.modules.alerts.alert_manager import AlertManager
from app.modules.positions.position_manager import PositionManager


# ---- AlertManager (in-memory) ---------------------------------------------------
def test_alert_default_thresholds_and_trigger_boundaries():
    def fires(z):
        m = AlertManager()          # fresh manager: no cooldown carry-over
        m.create_alert(1, "A", "B")
        return len(m.check_pair(1, z))
    a = AlertManager().create_alert(1, "A", "B")
    assert (a.threshold_high, a.threshold_low) == (2.0, -2.0)
    assert fires(1.99) == 0 and fires(-1.99) == 0
    assert fires(2.0) == 1      # >= inclusive
    assert fires(-2.0) == 1     # <= inclusive
    assert AlertManager().check_pair(999, 5) == []


def test_alert_disabled_and_update():
    m = AlertManager()
    a = m.create_alert(1, "A", "B", threshold_high=3)
    assert a.threshold_low is None
    assert m.check_pair(1, -10) == []          # low threshold unset
    m.update_alert(a.alert_id, enabled=False)
    assert m.check_pair(1, 10) == []
    m.update_alert(a.alert_id, enabled=True, threshold_high=1.0)
    a.last_triggered = None
    assert len(m.check_pair(1, 1.0)) == 1
    assert m.update_alert(12345, enabled=True) is None


def test_alert_delete_cleans_pair_index():
    m = AlertManager()
    a = m.create_alert(7, "A", "B")
    assert m.delete_alert(a.alert_id) is True and m.delete_alert(a.alert_id) is False
    assert m.get_alerts(pair_id=7) == [] and m.check_pair(7, 9) == []


def test_alert_check_all_pairs_handles_none_zscore():
    m = AlertManager()
    m.create_alert(1, "A", "B")
    r = m.check_all_pairs([{"id": 1, "current_zscore": None}, {"id": 1, "current_zscore": 2.5},
                           {"current_zscore": 9}])
    assert list(r) == [1]


def test_alert_cooldown_dedupes_repeated_checks():
    m = AlertManager()
    a = m.create_alert(1, "A", "B")
    for _ in range(5):
        m.check_pair(1, 3.0)
    assert a.trigger_count == 1


def test_alert_refires_after_cooldown():
    from datetime import datetime, timedelta
    from app.modules.alerts.alert_manager import ALERT_COOLDOWN_SECONDS
    m = AlertManager()
    a = m.create_alert(1, "A", "B")
    assert len(m.check_pair(1, 3.0)) == 1 and a.last_triggered is not None
    a.last_triggered = datetime.utcnow() - timedelta(seconds=ALERT_COOLDOWN_SECONDS + 1)
    assert len(m.check_pair(1, 3.0)) == 1 and a.trigger_count == 2


# ---- PositionManager ----------------------------------------------------------------
def test_position_manager_pnl_golden():
    m = PositionManager()
    kw = dict(pair_id=1, asset_a="A", asset_b="B", quantity_a=10, quantity_b=20,
              entry_price_a=100, entry_price_b=50, beta=0.5, entry_zscore=-2)
    lg = m.create_position(side="long", **kw)
    sh = m.create_position(side="short", **kw)
    # long: A 100->110 (+100), short B 50->45 (+100) => 200
    r = m.calculate_pnl(lg.position_id, 110, 45)
    assert (r["pnl_a"], r["pnl_b"], r["total_pnl"]) == (100, 100, 200)
    r = m.calculate_pnl(sh.position_id, 110, 45)
    assert (r["pnl_a"], r["pnl_b"], r["total_pnl"]) == (-100, -100, -200)
    assert m.calculate_pnl(999, 1, 1) is None
    assert m.delete_position(lg.position_id) and not m.delete_position(lg.position_id)
    assert [p.position_id for p in m.get_positions()] == [sh.position_id]


# ---- API CRUD (DB-backed routes) -----------------------------------------------------
def _pair():
    from test_api_security import _seed_pair
    return _seed_pair()


def test_alert_api_crud_roundtrip(client, auth):
    pid, a, b = _pair()
    q = {"pair_id": pid, "asset_a": a, "asset_b": b}
    c = client.post("/api/v1/alerts/", params=q, headers=auth).json()
    assert (c["threshold_high"], c["threshold_low"], c["enabled"]) == (2.0, -2.0, True)
    aid = c["alert_id"]
    assert client.get(f"/api/v1/alerts/{aid}", headers=auth).json()["pair_id"] == pid
    u = client.put(f"/api/v1/alerts/{aid}", params={"threshold_high": 3.5, "enabled": "false"},
                   headers=auth).json()
    assert u["threshold_high"] == 3.5 and u["enabled"] is False
    lst = client.get("/api/v1/alerts/", params={"pair_id": pid}, headers=auth).json()
    assert aid in [x["alert_id"] for x in lst["alerts"]] and lst["total"] == len(lst["alerts"])
    assert client.delete(f"/api/v1/alerts/{aid}", headers=auth).status_code == 200
    assert client.delete(f"/api/v1/alerts/{aid}", headers=auth).status_code == 404
    assert client.get(f"/api/v1/alerts/{aid}", headers=auth).status_code == 404
    assert client.put(f"/api/v1/alerts/{aid}", params={"enabled": "true"}, headers=auth).status_code == 404


def test_alert_api_duplicate_create_is_not_deduped(client, auth):
    """Documents BUG-4: identical alert definitions are accepted twice (no uniqueness check)."""
    pid, a, b = _pair()
    q = {"pair_id": pid, "asset_a": a, "asset_b": b}
    ids = [client.post("/api/v1/alerts/", params=q, headers=auth).json()["alert_id"] for _ in range(2)]
    assert ids[0] != ids[1]
    for i in ids:
        client.delete(f"/api/v1/alerts/{i}", headers=auth)


def test_db_alert_fires_in_triggered_check(client, auth, monkeypatch):
    from app.modules.screener import live_screener as ls
    pid, a, b = _pair()
    aid = client.post("/api/v1/alerts/", params={"pair_id": pid, "asset_a": a, "asset_b": b},
                      headers=auth).json()["alert_id"]
    monkeypatch.setattr(ls.get_live_screener(), "current_results",
                        [{"id": pid, "asset_a": a, "asset_b": b, "current_zscore": 5.0}])
    r = client.get("/api/v1/alerts/triggered/check", headers=auth)
    client.delete(f"/api/v1/alerts/{aid}", headers=auth)
    assert aid in [t["alert_id"] for t in r.json()["triggered"]]


def test_alert_api_validation(client, auth):
    assert client.post("/api/v1/alerts/", params={"pair_id": 1}, headers=auth).status_code == 422
    pid, a, b = _pair()
    bad = client.post("/api/v1/alerts/", params={"pair_id": pid, "asset_a": "bad sym!", "asset_b": b},
                      headers=auth)
    assert bad.status_code == 422
    assert client.post("/api/v1/alerts/", params={"pair_id": pid, "asset_a": a, "asset_b": b,
                                                  "threshold_high": "abc"}, headers=auth).status_code == 422


def _pos_body(pid, a, b, **over):
    body = dict(pair_id=pid, asset_a=a, asset_b=b, side="long", quantity_a=10, quantity_b=20,
                entry_price_a=100, entry_price_b=50, beta=0.5, entry_zscore=-2)
    body.update(over)
    return body


def test_position_api_crud_and_pnl_golden(client, auth):
    pid, a, b = _pair()
    r = client.post("/api/v1/positions/", json=_pos_body(pid, a, b), headers=auth)
    assert r.status_code == 200
    pos = r.json()["position_id"]
    assert client.get(f"/api/v1/positions/{pos}", headers=auth).status_code == 200
    lst = client.get("/api/v1/positions/", headers=auth).json()
    assert pos in [p["position_id"] for p in lst["positions"]]
    pnl = client.get(f"/api/v1/positions/{pos}/pnl", params={"current_price_a": 110, "current_price_b": 45},
                     headers=auth).json()
    assert (pnl["pnl_a"], pnl["pnl_b"], pnl["total_pnl"]) == (100, 100, 200)
    assert client.delete(f"/api/v1/positions/{pos}", headers=auth).status_code == 200
    assert client.delete(f"/api/v1/positions/{pos}", headers=auth).status_code == 404
    assert client.get(f"/api/v1/positions/{pos}/pnl", params={"current_price_a": 1, "current_price_b": 1},
                      headers=auth).status_code == 404


@pytest.mark.parametrize("over", [dict(side="flat"), dict(quantity_a=0), dict(quantity_b=-1),
                                  dict(entry_price_a=0), dict(beta=0)])
def test_position_api_rejects_invalid(client, auth, over):
    pid, a, b = _pair()
    assert client.post("/api/v1/positions/", json=_pos_body(pid, a, b, **over), headers=auth).status_code == 422


# ---- auth matrix ------------------------------------------------------------------------
PROTECTED = [("GET", "/api/v1/screener/status"), ("GET", "/api/v1/screener/results"),
             ("GET", "/api/v1/screener/export/csv"), ("GET", "/api/v1/screener/export/excel"),
             ("GET", "/api/v1/alerts/"), ("GET", "/api/v1/positions/"),
             ("GET", "/api/v1/backtester/sessions"), ("GET", "/api/v1/live/snapshot"),
             ("POST", "/api/v1/screener/run-live")]


@pytest.mark.parametrize("method,path", PROTECTED)
def test_auth_matrix_protected_routes(client, method, path):
    assert client.request(method, path).status_code == 401
    assert client.request(method, path, headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.request(method, path, headers={"X-API-Key": ""}).status_code == 401
    # the cron secret must not unlock regular API routes
    assert client.request(method, path, headers={"Authorization": "Bearer cron-secret"}).status_code == 401


def test_auth_matrix_cron(client, monkeypatch):
    from app.api import security
    from app.modules.screener import live_screener as ls
    calls = []
    monkeypatch.setattr(ls.get_live_screener(), "_run_screening", lambda: calls.append(1))
    monkeypatch.setattr(security.expensive_limit, "limit", 1000)  # relax 6/min limiter for this test
    p = "/api/v1/screener/cron/run"
    assert client.get(p).status_code == 401
    assert client.get(p, headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.get(p, headers={"Authorization": "cron-secret"}).status_code == 401   # no Bearer prefix
    assert client.get(p, headers={"X-API-Key": "nope"}).status_code == 401
    assert client.get(p, headers={"X-API-Key": "test-key"}).status_code == 200          # API key accepted
    assert client.post(p, headers={"Authorization": "Bearer cron-secret"}).status_code == 200
    assert len(calls) == 2


def test_expensive_endpoint_rate_limited(client, auth, monkeypatch):
    from app.api import security
    monkeypatch.setattr(security.expensive_limit, "hits", type(security.expensive_limit.hits)(
        security.expensive_limit.hits.default_factory))
    monkeypatch.setattr(security.expensive_limit, "limit", 2)
    from app.modules.screener import live_screener as ls
    monkeypatch.setattr(ls.get_live_screener(), "_run_screening", lambda: None)
    h = {"Authorization": "Bearer cron-secret"}
    codes = [client.get("/api/v1/screener/cron/run", headers=h).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


# ---- exports ---------------------------------------------------------------------------------
@pytest.fixture()
def live_results(monkeypatch):
    from app.modules.screener import live_screener as ls
    rows = [dict(id=1, asset_a="AAA", asset_b="BBB", correlation=0.9, beta=1.2, adf_pvalue=0.01,
                 current_zscore=2.1),
            dict(id=2, asset_a="CCC", asset_b="DDD", correlation=0.5, beta=0.7, adf_pvalue=0.04,
                 current_zscore=-1.0)]
    monkeypatch.setattr(ls.get_live_screener(), "current_results", rows)
    return rows


def test_export_csv_golden(client, auth, live_results):
    r = client.get("/api/v1/screener/export/csv", headers=auth)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "attachment; filename=pairs_screener_" in r.headers["content-disposition"]
    lines = r.text.strip().splitlines()
    assert lines[0] == "asset_a,asset_b,correlation,beta,adf_pvalue,current_zscore"
    assert lines[1] == "AAA,BBB,0.9,1.2,0.01,2.1" and len(lines) == 3
    f = client.get("/api/v1/screener/export/csv", params={"min_correlation": 0.8}, headers=auth)
    assert len(f.text.strip().splitlines()) == 2
    one = client.get("/api/v1/screener/export/csv", params={"limit": 1}, headers=auth)
    assert len(one.text.strip().splitlines()) == 2


def test_export_excel_roundtrip(client, auth, live_results):
    r = client.get("/api/v1/screener/export/excel", headers=auth)
    assert r.status_code == 200 and "spreadsheetml" in r.headers["content-type"]
    df = pd.read_excel(io.BytesIO(r.content), sheet_name="Pairs")
    assert list(df["asset_a"]) == ["AAA", "CCC"] and df["beta"].iloc[0] == pytest.approx(1.2)


def test_export_empty_results_does_not_500(client, auth, monkeypatch):
    from app.modules.screener import live_screener as ls
    monkeypatch.setattr(ls.get_live_screener(), "current_results", [])
    assert client.get("/api/v1/screener/export/csv", headers=auth).status_code == 200
    assert client.get("/api/v1/screener/export/excel", headers=auth).status_code == 200


# ---- scheduler overlap --------------------------------------------------------------------------
def test_live_screener_overlap_is_skipped(monkeypatch):
    """A second _run_screening while one is in flight must not start a second scan."""
    from app.modules.screener import live_screener as ls
    started = threading.Event()
    release = threading.Event()
    n = []

    class Slow:
        def __init__(self, db=None):
            pass

        def screen_pairs(self, cfg, session_id=None, return_stats=False):
            n.append(1)
            started.set()
            release.wait(5)
            return {"results": [{"id": 1, "asset_a": "A", "asset_b": "B", "correlation": .9}],
                    "stats": {"pairs_generated": 3}}

    monkeypatch.setattr(ls, "PairsScreener", Slow)
    monkeypatch.setattr(ls, "SessionLocal", None)
    s = ls.LiveScreener()
    t = threading.Thread(target=s._run_screening)
    t.start()
    assert started.wait(5) and s.is_running
    s._run_screening()                       # overlapping call returns immediately
    assert n == [1]
    with pytest.raises(ValueError):
        s.run_manual()
    release.set()
    t.join(5)
    assert not s.is_running and s.get_results()[0]["id"] == 1 and len(n) == 1
    assert s.get_last_session()["total_pairs_tested"] == 3


def test_live_screener_failure_resets_flag_and_keeps_old_results(monkeypatch):
    from app.modules.screener import live_screener as ls

    class Boom:
        def __init__(self, db=None):
            pass

        def screen_pairs(self, *a, **k):
            raise RuntimeError("exchange down")

    class Empty(Boom):
        def screen_pairs(self, *a, **k):
            return {"results": [], "stats": {"pairs_generated": 0}}

    monkeypatch.setattr(ls, "SessionLocal", None)
    s = ls.LiveScreener()
    s.current_results = [{"id": 9}]
    monkeypatch.setattr(ls, "PairsScreener", Boom)
    s._run_screening()
    assert not s.is_running and s.get_results() == [{"id": 9}]
    monkeypatch.setattr(ls, "PairsScreener", Empty)
    s._run_screening()
    assert s.get_results() == [{"id": 9}]      # degraded empty run does not wipe good data


def test_live_screener_start_loop_actually_runs(monkeypatch):
    from app.modules.screener import live_screener as ls
    ran = threading.Event()

    class Q:
        def __init__(self, db=None):
            pass

        def screen_pairs(self, *a, **k):
            ran.set()
            return {"results": [], "stats": {}}

    monkeypatch.setattr(ls, "PairsScreener", Q)
    monkeypatch.setattr(ls, "SessionLocal", None)
    s = ls.LiveScreener()
    s.start()
    try:
        assert ran.wait(3)
    finally:
        s.is_running = False


def test_run_endpoint_rejects_overlap_with_live_scan(client, auth, monkeypatch):
    from app.api import routes, security
    from app.modules.screener import live_screener as ls
    monkeypatch.setattr(security.expensive_limit, "limit", 1000)
    started = []
    monkeypatch.setattr(routes, "_run_screening_background", lambda sid, cfg: started.append(sid))
    monkeypatch.setattr(ls.get_live_screener(), "is_running", True)
    body = {"assets": ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE"], "lookback_days": 60, "max_assets": 10}
    r = client.post("/api/v1/screener/run", json=body, headers=auth)
    assert r.status_code == 400 and started == []


def test_alert_matches_by_assets_not_rank(client, auth, monkeypatch):
    """R-05: after a rescan the rank id changes; the alert must follow (asset_a, asset_b)."""
    from app.modules.screener import live_screener as ls
    pid, a, b = _pair()
    aid = client.post("/api/v1/alerts/", params={"pair_id": pid, "asset_a": a, "asset_b": b},
                      headers=auth).json()["alert_id"]
    scr = ls.get_live_screener()
    monkeypatch.setattr(scr, "current_results", [
        {"id": pid, "asset_a": "ZZZ", "asset_b": "YYY", "current_zscore": 9.0},   # same rank, other pair
        {"id": pid + 50, "asset_a": a, "asset_b": b, "current_zscore": 5.0},
    ])
    r = client.get("/api/v1/alerts/triggered/check", headers=auth).json()
    hits = [t for t in r["triggered"] if t["alert_id"] == aid]
    assert len(hits) == 1 and hits[0]["current_zscore"] == 5.0
    monkeypatch.setattr(scr, "current_results",
                        [{"id": pid, "asset_a": "ZZZ", "asset_b": "YYY", "current_zscore": 9.0}])
    r = client.get("/api/v1/alerts/triggered/check", headers=auth).json()
    assert aid not in [t["alert_id"] for t in r["triggered"]]
    client.delete(f"/api/v1/alerts/{aid}", headers=auth)


def test_alert_manager_check_assets():
    m = AlertManager()
    m.create_alert(3, "A", "B")
    assert m.check_assets("A", "C", 9) == []
    assert len(m.check_assets("A", "B", 9)) == 1

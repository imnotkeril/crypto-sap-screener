import json

from app.modules.screener import snapshot_store
from app.modules.screener.live_screener import LiveScreener


def test_disabled_without_token(monkeypatch):
    monkeypatch.delenv("BLOB_READ_WRITE_TOKEN", raising=False)
    assert not snapshot_store.enabled()
    assert snapshot_store.save_snapshot({"results": []}) is False
    assert snapshot_store.load_snapshot() is None


def test_public_url_derived_from_token(monkeypatch):
    monkeypatch.delenv("SNAPSHOT_URL", raising=False)
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "vercel_blob_rw_AbC123_secretpart")
    assert snapshot_store._public_url() == "https://abc123.public.blob.vercel-storage.com/sap/snapshot.json"


def test_screener_restores_from_snapshot(monkeypatch):
    snap = {
        "results": [{"asset_a": "ETH", "asset_b": "SOL", "correlation": 0.88}],
        "session": {"id": 1, "completed_at": "2026-11-17T08:00:00", "status": "completed"},
    }
    monkeypatch.setattr(snapshot_store, "load_snapshot", lambda: snap)
    ls = LiveScreener.__new__(LiveScreener)
    ls.current_results, ls.last_session_info, ls.last_screening_time = [], None, None
    ls._load_from_snapshot()
    assert ls.current_results[0]["asset_a"] == "ETH"
    assert ls.last_screening_time.year == 2026


def test_save_serializes_datetimes(monkeypatch):
    from datetime import datetime
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "vercel_blob_rw_abc_secret")
    sent = {}

    def fake_put(path, body, **kw):
        sent["body"] = body

    import vercel.blob.sync as vs
    monkeypatch.setattr(vs, "put_blob", fake_put)
    assert snapshot_store.save_snapshot({"results": [{"d": datetime(2026, 1, 1)}]})
    assert json.loads(sent["body"])["results"][0]["d"].startswith("2026-01-01")

"""R-04: UI settings sent to /run must reach the screener config."""
from app.api import routes


def test_run_passes_all_ui_fields(client, auth, monkeypatch):
    seen = {}
    monkeypatch.setattr(routes, "_run_screening_background",
                        lambda sid, cfg: seen.setdefault("cfg", cfg))
    body = {"use_fdr": True, "min_half_life": 2, "max_half_life": 30, "use_clustering": True,
            "cluster_distance": 0.4, "taker_fee_bps": 7, "slippage_bps": 3,
            "funding_bps_per_8h": 2, "entry_zscore": 2.5}
    r = client.post("/api/v1/screener/run", json=body, headers=auth)
    assert r.status_code == 200, r.text
    cfg = seen["cfg"]
    for k, v in body.items():
        assert getattr(cfg, k) == v


def test_run_rejects_out_of_range(client, auth):
    r = client.post("/api/v1/screener/run", json={"taker_fee_bps": -1}, headers=auth)
    assert r.status_code == 422

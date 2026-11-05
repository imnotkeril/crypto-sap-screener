"""S-01: asset symbols become cache filenames; reject traversal/odd input at every entry point."""
import pytest

from app.modules.screener.data_loader import DataLoader

BS = chr(92)  # backslash: a path separator on Windows hosts


@pytest.mark.parametrize("sym", [BS + ".." + BS + "evil", "../x", "C:" + BS + "x", "BT C", "A" * 21, "", "a/b"])
def test_backtest_rejects_bad_symbol(client, auth, sym):
    r = client.post("/api/v1/backtester/run", json={"asset_a": sym, "asset_b": "ETH"}, headers=auth)
    assert r.status_code == 422


def test_screener_run_rejects_bad_assets(client, auth):
    r = client.post("/api/v1/screener/run", json={"assets": ["BTC", ".." + BS + "x"]}, headers=auth)
    assert r.status_code == 422


def test_loader_refuses_path_like_symbol_without_touching_disk():
    dl = object.__new__(DataLoader)
    assert dl.get_price_series(".." + BS + ".." + BS + "evil", days=30).empty
    assert dl.get_price_series("a/b", days=30).empty

from pathlib import Path
from unittest.mock import patch

from app.modules.screener.data_loader import DataLoader


def test_cache_dir_uses_preferred_when_writable(tmp_path):
    target = tmp_path / "cache" / "price_data"
    assert DataLoader._resolve_cache_dir(target) == target
    assert target.is_dir()


def test_cache_dir_falls_back_to_tmp_on_read_only_fs(tmp_path):
    real_mkdir = Path.mkdir

    def fake_mkdir(self, *a, **k):
        if "cache" in self.parts and "price_data" in self.parts:
            raise OSError(30, "Read-only file system")
        return real_mkdir(self, *a, **k)

    with patch.object(Path, "mkdir", fake_mkdir):
        out = DataLoader._resolve_cache_dir(Path("cache/price_data"))
    assert out.name == "sap_price_cache"

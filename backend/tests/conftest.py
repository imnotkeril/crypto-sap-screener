import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="statarb-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_tmp / 'test.db').as_posix()}"
os.environ["API_KEY"] = "test-key"
os.environ["CRON_SECRET"] = "cron-secret"
os.environ["AUTO_SCREEN_ON_COLD_START"] = "false"
os.environ["CORS_ORIGINS"] = "http://allowed.example"
os.environ.pop("REDIS_URL", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth():
    return {"X-API-Key": "test-key"}

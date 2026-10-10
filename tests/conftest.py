import httpx
import pytest

from pulse.config import Monitor, Settings
from pulse.db import Check, Database

NOW = 1_760_000_000  # fixed "current time" so tests never depend on the real clock


@pytest.fixture
def db():
    database = Database(":memory:")
    yield database
    database.close()


@pytest.fixture
def monitor():
    return Monitor(name="Main site", url="https://example.com", interval=60, timeout=5)


@pytest.fixture
def settings(monitor):
    api = Monitor(name="API", url="https://api.example.com/health", expect_text="ok")
    return Settings(monitors=[monitor, api], title="Example status", failure_threshold=2)


def make_check(ok=True, ts=NOW, monitor="main-site", latency=100.0, error=None):
    if ok:
        return Check(monitor, ts, True, 200, latency, None)
    return Check(monitor, ts, False, 500, None, error or "expected status 200, got 500")


def client_returning(handler):
    """An httpx client whose requests are answered by ``handler`` instead of the network."""
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))

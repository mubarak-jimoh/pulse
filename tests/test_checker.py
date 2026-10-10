import httpx

from pulse.checker import USER_AGENT, run_check
from pulse.config import Monitor

from .conftest import NOW, client_returning


async def test_passes_on_expected_status(monitor):
    client = client_returning(lambda request: httpx.Response(200, text="hello"))
    check = await run_check(client, monitor, NOW)
    assert check.ok and check.status_code == 200 and check.error is None
    assert check.latency_ms is not None and check.ts == NOW
    assert check.monitor == "main-site"


async def test_fails_on_wrong_status(monitor):
    client = client_returning(lambda request: httpx.Response(503))
    check = await run_check(client, monitor, NOW)
    assert not check.ok
    assert check.status_code == 503
    assert check.error == "expected status 200, got 503"


async def test_custom_expected_status():
    monitor = Monitor(name="Teapot", url="https://example.com", expect_status=418)
    client = client_returning(lambda request: httpx.Response(418))
    assert (await run_check(client, monitor, NOW)).ok


async def test_fails_when_text_missing():
    monitor = Monitor(name="API", url="https://example.com", expect_text="healthy")
    client = client_returning(lambda request: httpx.Response(200, text="maintenance"))
    check = await run_check(client, monitor, NOW)
    assert not check.ok and "healthy" in check.error


async def test_passes_when_text_present():
    monitor = Monitor(name="API", url="https://example.com", expect_text="healthy")
    client = client_returning(lambda request: httpx.Response(200, text='{"status": "healthy"}'))
    assert (await run_check(client, monitor, NOW)).ok


async def test_timeout_is_a_failure_not_a_crash(monitor):
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    check = await run_check(client_returning(handler), monitor, NOW)
    assert not check.ok and check.status_code is None
    assert check.error == "timed out after 5s"


async def test_connection_error(monitor):
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    check = await run_check(client_returning(handler), monitor, NOW)
    assert not check.ok and check.error == "could not connect"


async def test_follows_redirects(monitor):
    def handler(request):
        if request.url.path == "/":
            return httpx.Response(301, headers={"Location": "https://example.com/home"})
        return httpx.Response(200)

    assert (await run_check(client_returning(handler), monitor, NOW)).ok


async def test_sends_user_agent(monitor):
    seen = {}

    def handler(request):
        seen["agent"] = request.headers["user-agent"]
        return httpx.Response(200)

    await run_check(client_returning(handler), monitor, NOW)
    assert seen["agent"] == USER_AGENT

"""Run a single HTTP check against a monitor."""

from __future__ import annotations

import time

import httpx

from .config import Monitor
from .db import Check

USER_AGENT = "pulse-uptime-monitor/1.0"


async def run_check(client: httpx.AsyncClient, monitor: Monitor, now: int | None = None) -> Check:
    """Request the monitor's URL and decide whether it counts as up.

    A check passes only if the request completes inside the timeout, the status
    code matches, and (when configured) the expected text is in the body.
    """
    ts = int(time.time()) if now is None else now
    started = time.perf_counter()

    try:
        response = await client.get(
            monitor.url,
            timeout=monitor.timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
    except httpx.TimeoutException:
        return Check(monitor.slug, ts, False, None, None, f"timed out after {monitor.timeout:g}s")
    except httpx.HTTPError as exc:
        return Check(monitor.slug, ts, False, None, None, _describe(exc))

    latency_ms = round((time.perf_counter() - started) * 1000, 1)

    if response.status_code != monitor.expect_status:
        error = f"expected status {monitor.expect_status}, got {response.status_code}"
        return Check(monitor.slug, ts, False, response.status_code, latency_ms, error)

    if monitor.expect_text and monitor.expect_text not in response.text:
        error = f"response did not contain '{monitor.expect_text}'"
        return Check(monitor.slug, ts, False, response.status_code, latency_ms, error)

    return Check(monitor.slug, ts, True, response.status_code, latency_ms, None)


def _describe(exc: httpx.HTTPError) -> str:
    """Short, readable reason for a failed request."""
    if isinstance(exc, httpx.ConnectError):
        return "could not connect"
    if isinstance(exc, httpx.TooManyRedirects):
        return "too many redirects"
    return type(exc).__name__

"""Uptime and latency numbers worked out from stored checks."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .db import Check

DAY = 86_400


def uptime(checks: list[Check]) -> float | None:
    """Percentage of checks that passed, or None when there is no data."""
    if not checks:
        return None
    return round(100 * sum(c.ok for c in checks) / len(checks), 3)


def percentile(values: list[float], pct: float) -> float | None:
    """Nearest-rank percentile. ``pct`` is 0 to 100."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100 * len(ordered)))
    return ordered[rank - 1]


@dataclass(frozen=True)
class DayBucket:
    start: int
    total: int
    failed: int

    @property
    def state(self) -> str:
        if self.total == 0:
            return "nodata"
        if self.failed == 0:
            return "up"
        return "down" if self.failed / self.total >= 0.5 else "degraded"

    @property
    def uptime(self) -> float | None:
        if self.total == 0:
            return None
        return round(100 * (self.total - self.failed) / self.total, 2)


def daily_buckets(checks: list[Check], now: int, days: int = 90) -> list[DayBucket]:
    """One bucket per UTC day, oldest first, ending with today."""
    today = now - now % DAY
    first = today - (days - 1) * DAY
    totals = [0] * days
    failed = [0] * days

    for check in checks:
        index = (check.ts - first) // DAY
        if 0 <= index < days:
            totals[index] += 1
            failed[index] += not check.ok

    return [DayBucket(first + i * DAY, totals[i], failed[i]) for i in range(days)]


@dataclass(frozen=True)
class Summary:
    uptime_24h: float | None
    uptime_7d: float | None
    uptime_30d: float | None
    p50_ms: float | None
    p95_ms: float | None


def summarise(checks: list[Check], now: int) -> Summary:
    """Headline numbers. ``checks`` should cover at least the last 30 days."""

    def window(days: int) -> list[Check]:
        return [c for c in checks if c.ts >= now - days * DAY]

    last_day = window(1)
    latencies = [c.latency_ms for c in last_day if c.ok and c.latency_ms is not None]
    return Summary(
        uptime_24h=uptime(last_day),
        uptime_7d=uptime(window(7)),
        uptime_30d=uptime(window(30)),
        p50_ms=percentile(latencies, 50),
        p95_ms=percentile(latencies, 95),
    )

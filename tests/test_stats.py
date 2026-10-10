import pytest

from pulse import stats
from pulse.stats import DAY

from .conftest import NOW, make_check


def test_uptime_with_no_data_is_none():
    assert stats.uptime([]) is None


def test_uptime_percentage():
    checks = [make_check(ok=True)] * 3 + [make_check(ok=False)]
    assert stats.uptime(checks) == 75.0


@pytest.mark.parametrize("pct, expected", [(50, 30), (95, 50), (100, 50), (1, 10)])
def test_percentile_nearest_rank(pct, expected):
    assert stats.percentile([50, 10, 40, 20, 30], pct) == expected


def test_percentile_empty():
    assert stats.percentile([], 95) is None


def test_daily_buckets_cover_the_window():
    buckets = stats.daily_buckets([], NOW, days=90)
    assert len(buckets) == 90
    assert buckets[-1].start == NOW - NOW % DAY
    assert all(b.state == "nodata" for b in buckets)


def test_daily_buckets_place_checks_on_the_right_day():
    checks = [make_check(ts=NOW), make_check(ok=False, ts=NOW - DAY), make_check(ts=NOW - 400 * DAY)]
    buckets = stats.daily_buckets(checks, NOW, days=7)
    assert (buckets[-1].total, buckets[-1].failed) == (1, 0)
    assert (buckets[-2].total, buckets[-2].failed) == (1, 1)
    assert sum(b.total for b in buckets) == 2  # the very old check is outside the window


@pytest.mark.parametrize(
    "total, failed, state",
    [(0, 0, "nodata"), (10, 0, "up"), (10, 1, "degraded"), (10, 5, "down"), (10, 10, "down")],
)
def test_bucket_state(total, failed, state):
    assert stats.DayBucket(0, total, failed).state == state


def test_summary_windows():
    checks = [
        make_check(ok=False, ts=NOW - 20 * DAY),
        make_check(ok=False, ts=NOW - 3 * DAY),
        make_check(ok=True, ts=NOW - 3600, latency=120),
        make_check(ok=True, ts=NOW - 60, latency=80),
    ]
    summary = stats.summarise(checks, NOW)
    assert summary.uptime_24h == 100.0
    assert summary.uptime_7d == pytest.approx(66.667)
    assert summary.uptime_30d == 50.0
    assert (summary.p50_ms, summary.p95_ms) == (80, 120)


def test_summary_ignores_failed_checks_in_latency():
    summary = stats.summarise([make_check(ok=False, ts=NOW - 60)], NOW)
    assert summary.p50_ms is None and summary.uptime_24h == 0.0

import pytest
from fastapi.testclient import TestClient

from pulse import incidents
from pulse.app import create_app, overall_state
from pulse.stats import DAY

from .conftest import NOW, make_check


@pytest.fixture
def client(settings, db):
    app = create_app(settings, db, run_scheduler=False, clock=lambda: NOW)
    with TestClient(app) as test_client:
        yield test_client


def test_healthz(client):
    assert client.get("/healthz").json()["monitors"] == 2


def test_status_is_pending_before_any_check(client):
    data = client.get("/api/status").json()
    assert data["state"] == "pending"
    assert [m["state"] for m in data["monitors"]] == ["pending", "pending"]
    assert len(data["monitors"][0]["days"]) == 90


def test_status_up(client, db):
    db.add_check(make_check(ts=NOW - 30))
    monitor = client.get("/api/status").json()["monitors"][0]
    assert monitor["state"] == "up"
    assert monitor["uptime_24h"] == 100.0
    assert monitor["last_checked"] == NOW - 30


def test_one_failure_is_degraded_not_down(client, db):
    incidents.record(db, make_check(ok=False, ts=NOW - 30))
    data = client.get("/api/status").json()
    assert data["monitors"][0]["state"] == "degraded"
    assert data["state"] == "degraded"
    assert data["incidents"] == []


def test_open_incident_is_down(client, db):
    for offset in (120, 60):
        incidents.record(db, make_check(ok=False, ts=NOW - offset))
    data = client.get("/api/status").json()
    assert data["state"] == "down"
    assert data["incidents"][0]["monitor"] == "Main site"
    assert data["incidents"][0]["resolved_at"] is None
    assert data["incidents"][0]["duration"] == 120


def test_old_resolved_incidents_drop_off(client, db):
    incident = db.start_incident("main-site", NOW - 40 * DAY, "boom")
    db.resolve_incident(incident.id, NOW - 39 * DAY)
    assert client.get("/api/status").json()["incidents"] == []


@pytest.mark.parametrize(
    "states, expected",
    [(["up", "up"], "up"), (["up", "degraded"], "degraded"), (["degraded", "down"], "down"),
     (["pending", "up"], "up"), (["pending"], "pending")],
)
def test_overall_state(states, expected):
    assert overall_state([{"state": s} for s in states]) == expected


def test_checks_endpoint(client, db):
    db.add_check(make_check(ts=NOW - 3600 * 30))
    db.add_check(make_check(ts=NOW - 60))
    assert len(client.get("/api/monitors/main-site/checks").json()["checks"]) == 1
    assert len(client.get("/api/monitors/main-site/checks?hours=48").json()["checks"]) == 2


def test_unknown_monitor_is_404(client):
    assert client.get("/api/monitors/nope/checks").status_code == 404
    assert client.get("/badge/nope.svg").status_code == 404


def test_hours_is_validated(client):
    assert client.get("/api/monitors/main-site/checks?hours=0").status_code == 422


def test_page_renders_and_escapes_html(settings, db):
    from dataclasses import replace

    from pulse.config import Monitor

    evil = Monitor(name="<script>alert(1)</script>", url="https://example.com")
    app = create_app(replace(settings, monitors=[evil]), db, run_scheduler=False, clock=lambda: NOW)
    with TestClient(app) as test_client:
        html = test_client.get("/").text
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert "Waiting for the first checks" in html


def test_page_shows_incident(client, db):
    for offset in (120, 60):
        incidents.record(db, make_check(ok=False, ts=NOW - offset))
    html = client.get("/").text
    assert "Service disruption" in html
    assert "ongoing for 2m" in html


def test_badge(client, db):
    assert "no data" in client.get("/badge/main-site.svg").text
    db.add_check(make_check(ts=NOW - 60))
    response = client.get("/badge/main-site.svg")
    assert response.headers["content-type"] == "image/svg+xml"
    assert "100.00%" in response.text

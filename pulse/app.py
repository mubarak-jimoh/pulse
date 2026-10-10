"""FastAPI app: the public status page, a JSON API and SVG badges."""

from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, Response

from . import __version__, config, page, stats
from .config import Monitor, Settings
from .db import Database
from .scheduler import Scheduler
from .stats import DAY


def monitor_status(db: Database, monitor: Monitor, now: int, days: int = 90) -> dict:
    checks = db.checks_since(monitor.slug, now - days * DAY)
    latest = checks[-1] if checks else None
    incident = db.open_incident(monitor.slug)

    if latest is None:
        state = "pending"
    elif incident is not None:
        state = "down"
    else:
        state = "up" if latest.ok else "degraded"

    return {
        "name": monitor.name,
        "slug": monitor.slug,
        "url": monitor.url,
        "state": state,
        "last_checked": latest.ts if latest else None,
        "last_error": latest.error if latest else None,
        **asdict(stats.summarise(checks, now)),
        "days": [
            {"date": b.start, "state": b.state, "uptime": b.uptime}
            for b in stats.daily_buckets(checks, now, days)
        ],
    }


def overall_state(monitors: list[dict]) -> str:
    states = {m["state"] for m in monitors}
    if "down" in states:
        return "down"
    if "degraded" in states:
        return "degraded"
    return "up" if "up" in states else "pending"


def create_app(settings: Settings, db: Database, run_scheduler: bool = True, clock=time.time) -> FastAPI:
    scheduler = Scheduler(settings, db) if run_scheduler else None

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if scheduler:
            scheduler.start()
        yield
        if scheduler:
            await scheduler.stop()

    app = FastAPI(title="Pulse", version=__version__, lifespan=lifespan)
    by_slug = {m.slug: m for m in settings.monitors}

    def snapshot() -> dict:
        now = int(clock())
        monitors = [monitor_status(db, m, now) for m in settings.monitors]
        incidents = [
            {
                "monitor": by_slug[i.monitor].name if i.monitor in by_slug else i.monitor,
                "started_at": i.started_at,
                "resolved_at": i.resolved_at,
                "duration": i.duration(now),
                "cause": i.cause,
            }
            for i in db.incidents_since(now - 30 * DAY)
        ]
        return {
            "title": settings.title,
            "state": overall_state(monitors),
            "generated_at": now,
            "monitors": monitors,
            "incidents": incidents,
        }

    @app.get("/", response_class=HTMLResponse)
    def status_page() -> str:
        return page.render(snapshot())

    @app.get("/api/status")
    def api_status() -> dict:
        return snapshot()

    @app.get("/api/monitors/{slug}/checks")
    def api_checks(slug: str, hours: int = Query(24, ge=1, le=24 * 90)) -> dict:
        if slug not in by_slug:
            raise HTTPException(404, "unknown monitor")
        checks = db.checks_since(slug, int(clock()) - hours * 3600)
        return {"monitor": slug, "hours": hours, "checks": [asdict(c) for c in checks]}

    @app.get("/badge/{slug}.svg")
    def badge(slug: str) -> Response:
        if slug not in by_slug:
            raise HTTPException(404, "unknown monitor")
        now = int(clock())
        value = stats.uptime(db.checks_since(slug, now - 30 * DAY))
        headers = {"Cache-Control": "max-age=300"}
        return Response(page.badge_svg(value), media_type="image/svg+xml", headers=headers)

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True, "version": __version__, "monitors": len(settings.monitors)}

    return app


def from_env() -> FastAPI:
    """Entry point for ``uvicorn pulse.app:from_env --factory``."""
    settings = config.load(os.environ.get("PULSE_CONFIG", "monitors.toml"))
    db = Database(os.environ.get("PULSE_DB", "pulse.db"))
    return create_app(settings, db)

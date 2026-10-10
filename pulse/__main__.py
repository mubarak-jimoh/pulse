"""Command line: ``python -m pulse serve | check | seed-demo``."""

from __future__ import annotations

import argparse
import asyncio
import logging
import random
import sys
import time

from . import config, incidents
from .app import create_app
from .db import Check, Database
from .scheduler import Scheduler
from .stats import DAY


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    settings = config.load(args.config)
    app = create_app(settings, Database(args.db))
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """Check every monitor once and print the result. Exit code 1 if any are down."""
    settings = config.load(args.config)
    db = Database(":memory:")

    async def run() -> bool:
        scheduler = Scheduler(settings, db)
        try:
            for monitor in settings.monitors:
                await scheduler.check_once(monitor)
        finally:
            await scheduler.client.aclose()
        all_ok = True
        for monitor in settings.monitors:
            check = db.latest_check(monitor.slug)
            if check.ok:
                print(f"  UP    {monitor.name}  {check.latency_ms:.0f} ms")
            else:
                all_ok = False
                print(f"  DOWN  {monitor.name}  {check.error}")
        return all_ok

    return 0 if asyncio.run(run()) else 1


def cmd_seed_demo(args: argparse.Namespace) -> int:
    """Fill the database with 90 days of made-up history so the page has something to show."""
    settings = config.load(args.config)
    db = Database(args.db)
    rng = random.Random(7)
    now = int(time.time())
    step = 600

    for index, monitor in enumerate(settings.monitors):
        base = 80 + index * 60
        outages = [(now - rng.randint(2, 85) * DAY, rng.randint(2, 9)) for _ in range(index + 1)]
        for ts in range(now - 90 * DAY, now, step):
            failing = any(start <= ts < start + length * step for start, length in outages)
            if failing:
                check = Check(monitor.slug, ts, False, 503, None, "expected status 200, got 503")
            else:
                latency = round(max(20.0, rng.gauss(base, base * 0.18)), 1)
                check = Check(monitor.slug, ts, True, 200, latency, None)
            incidents.record(db, check, settings.failure_threshold)

    print(f"seeded 90 days of demo history for {len(settings.monitors)} monitors into {args.db}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pulse", description="Self-hosted uptime monitor.")
    parser.add_argument("--config", default="monitors.toml", help="path to the monitors file")
    parser.add_argument("--db", default="pulse.db", help="path to the SQLite database")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="run the monitor and the status page")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.set_defaults(func=cmd_serve)

    sub.add_parser("check", help="check every monitor once and exit").set_defaults(func=cmd_check)
    sub.add_parser("seed-demo", help="add 90 days of fake history").set_defaults(func=cmd_seed_demo)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    try:
        return args.func(args)
    except config.ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

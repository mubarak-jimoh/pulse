"""Background loops that run each monitor on its own interval."""

from __future__ import annotations

import asyncio
import logging
import time

import httpx

from . import alerts, incidents
from .checker import run_check
from .config import Monitor, Settings
from .db import Database
from .stats import DAY

log = logging.getLogger("pulse.scheduler")


class Scheduler:
    def __init__(self, settings: Settings, db: Database, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self.db = db
        self.client = client or httpx.AsyncClient()
        self._tasks: list[asyncio.Task] = []

    async def check_once(self, monitor: Monitor, now: int | None = None) -> incidents.Transition | None:
        """Run one check, store it, and alert if the monitor changed state."""
        check = await run_check(self.client, monitor, now)
        transition = incidents.record(self.db, check, self.settings.failure_threshold)

        if transition and self.settings.webhook_url:
            message = alerts.build_message(monitor.name, monitor.url, transition)
            await alerts.notify(self.client, self.settings.webhook_url, message)
        return transition

    async def _loop(self, monitor: Monitor, delay: float) -> None:
        await asyncio.sleep(delay)
        while True:
            started = time.monotonic()
            try:
                await self.check_once(monitor)
            except Exception:  # one bad check must not kill the loop
                log.exception("check failed for %s", monitor.name)
            # Sleep for what is left of the interval so checks do not drift.
            await asyncio.sleep(max(0.0, monitor.interval - (time.monotonic() - started)))

    async def _prune_loop(self) -> None:
        while True:
            removed = self.db.prune(int(time.time()) - self.settings.retention_days * DAY)
            if removed:
                log.info("pruned %d old checks", removed)
            await asyncio.sleep(DAY)

    def start(self) -> None:
        monitors = self.settings.monitors
        for index, monitor in enumerate(monitors):
            # Spread the first checks out so they do not all fire in the same second.
            delay = index * min(1.0, monitor.interval / max(1, len(monitors)))
            self._tasks.append(asyncio.create_task(self._loop(monitor, delay)))
        self._tasks.append(asyncio.create_task(self._prune_loop()))

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        await self.client.aclose()

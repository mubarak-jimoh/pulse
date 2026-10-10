"""Turn a stream of check results into incidents.

One failed check is often just a blip, so an incident only opens after
``failure_threshold`` failures in a row. A single passing check resolves it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .db import Check, Database, Incident


@dataclass(frozen=True)
class Transition:
    kind: Literal["opened", "resolved"]
    incident: Incident


def record(db: Database, check: Check, failure_threshold: int = 2) -> Transition | None:
    """Store a check and return a transition if the monitor's state changed."""
    db.add_check(check)
    current = db.open_incident(check.monitor)

    if check.ok:
        if current is None:
            return None
        db.resolve_incident(current.id, check.ts)
        resolved = Incident(current.id, current.monitor, current.started_at, check.ts, current.cause)
        return Transition("resolved", resolved)

    if current is not None:
        return None

    recent = db.recent_checks(check.monitor, failure_threshold)
    if len(recent) < failure_threshold or any(c.ok for c in recent):
        return None

    # The outage began at the first failure of the streak, not when we noticed.
    started_at = recent[-1].ts
    return Transition("opened", db.start_incident(check.monitor, started_at, check.error))

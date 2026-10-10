"""Send a webhook when an incident opens or resolves.

The payload has both ``text`` and ``content`` so the same URL works with
Slack-style and Discord-style incoming webhooks.
"""

from __future__ import annotations

import logging

import httpx

from .incidents import Transition

log = logging.getLogger("pulse.alerts")


def format_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {secs}s" if secs else f"{minutes}m"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m" if minutes else f"{hours}h"


def build_message(name: str, url: str, transition: Transition) -> str:
    incident = transition.incident
    if transition.kind == "opened":
        reason = f" ({incident.cause})" if incident.cause else ""
        return f"DOWN: {name} is not responding{reason}. {url}"
    downtime = format_duration(incident.duration(incident.resolved_at or incident.started_at))
    return f"RECOVERED: {name} is back up after {downtime}. {url}"


async def notify(client: httpx.AsyncClient, webhook_url: str, message: str) -> bool:
    """Post the alert. A failed alert is logged, never raised: the monitor must keep running."""
    try:
        response = await client.post(webhook_url, json={"text": message, "content": message}, timeout=10)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("alert webhook failed: %s", exc)
        return False
    return True

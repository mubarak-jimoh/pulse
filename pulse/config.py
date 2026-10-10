"""Load and validate the monitor list from a TOML file."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse


class ConfigError(ValueError):
    """Raised when the config file is missing something or has a bad value."""


@dataclass(frozen=True)
class Monitor:
    name: str
    url: str
    interval: int = 60
    timeout: float = 10.0
    expect_status: int = 200
    expect_text: str | None = None

    @property
    def slug(self) -> str:
        return "".join(c if c.isalnum() else "-" for c in self.name.lower()).strip("-")


@dataclass(frozen=True)
class Settings:
    monitors: list[Monitor] = field(default_factory=list)
    title: str = "Service status"
    failure_threshold: int = 2
    webhook_url: str | None = None
    retention_days: int = 90


def _monitor(raw: dict, index: int) -> Monitor:
    for key in ("name", "url"):
        if not raw.get(key):
            raise ConfigError(f"monitor #{index + 1} is missing '{key}'")

    parsed = urlparse(raw["url"])
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ConfigError(f"monitor '{raw['name']}' has an invalid url: {raw['url']}")

    interval = int(raw.get("interval", 60))
    if interval < 5:
        raise ConfigError(f"monitor '{raw['name']}': interval must be at least 5 seconds")

    timeout = float(raw.get("timeout", 10))
    if timeout <= 0 or timeout >= interval:
        raise ConfigError(f"monitor '{raw['name']}': timeout must be between 0 and the interval")

    return Monitor(
        name=raw["name"],
        url=raw["url"],
        interval=interval,
        timeout=timeout,
        expect_status=int(raw.get("expect_status", 200)),
        expect_text=raw.get("expect_text"),
    )


def parse(data: dict) -> Settings:
    monitors = [_monitor(raw, i) for i, raw in enumerate(data.get("monitor", []))]
    if not monitors:
        raise ConfigError("no monitors defined: add at least one [[monitor]] block")

    slugs = [m.slug for m in monitors]
    duplicates = {s for s in slugs if slugs.count(s) > 1}
    if duplicates:
        raise ConfigError(f"monitor names must be unique, found duplicates: {sorted(duplicates)}")

    threshold = int(data.get("failure_threshold", 2))
    if threshold < 1:
        raise ConfigError("failure_threshold must be 1 or more")

    return Settings(
        monitors=monitors,
        title=data.get("title", "Service status"),
        failure_threshold=threshold,
        webhook_url=data.get("webhook_url"),
        retention_days=int(data.get("retention_days", 90)),
    )


def load(path: str | Path) -> Settings:
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"config file not found: {path}")
    with path.open("rb") as handle:
        return parse(tomllib.load(handle))

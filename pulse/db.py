"""SQLite storage for check results and incidents.

All timestamps are Unix seconds in UTC. Passing ``now`` in from the caller
keeps every query testable without patching the clock.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS checks (
    id          INTEGER PRIMARY KEY,
    monitor     TEXT    NOT NULL,
    ts          INTEGER NOT NULL,
    ok          INTEGER NOT NULL,
    status_code INTEGER,
    latency_ms  REAL,
    error       TEXT
);
CREATE INDEX IF NOT EXISTS idx_checks_monitor_ts ON checks (monitor, ts);

CREATE TABLE IF NOT EXISTS incidents (
    id          INTEGER PRIMARY KEY,
    monitor     TEXT    NOT NULL,
    started_at  INTEGER NOT NULL,
    resolved_at INTEGER,
    cause       TEXT
);
CREATE INDEX IF NOT EXISTS idx_incidents_monitor ON incidents (monitor, started_at);
"""


@dataclass(frozen=True)
class Check:
    monitor: str
    ts: int
    ok: bool
    status_code: int | None
    latency_ms: float | None
    error: str | None


@dataclass(frozen=True)
class Incident:
    id: int
    monitor: str
    started_at: int
    resolved_at: int | None
    cause: str | None

    def duration(self, now: int) -> int:
        return (self.resolved_at or now) - self.started_at


class Database:
    def __init__(self, path: str | Path = "pulse.db") -> None:
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    # --- checks ---

    def add_check(self, check: Check) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO checks (monitor, ts, ok, status_code, latency_ms, error)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (check.monitor, check.ts, int(check.ok), check.status_code, check.latency_ms, check.error),
            )

    def checks_since(self, monitor: str, since: int) -> list[Check]:
        rows = self.conn.execute(
            "SELECT * FROM checks WHERE monitor = ? AND ts >= ? ORDER BY ts", (monitor, since)
        ).fetchall()
        return [self._check(row) for row in rows]

    def latest_check(self, monitor: str) -> Check | None:
        row = self.conn.execute(
            "SELECT * FROM checks WHERE monitor = ? ORDER BY ts DESC, id DESC LIMIT 1", (monitor,)
        ).fetchone()
        return self._check(row) if row else None

    def recent_checks(self, monitor: str, limit: int) -> list[Check]:
        """The last ``limit`` checks, newest first."""
        rows = self.conn.execute(
            "SELECT * FROM checks WHERE monitor = ? ORDER BY ts DESC, id DESC LIMIT ?", (monitor, limit)
        ).fetchall()
        return [self._check(row) for row in rows]

    def prune(self, before: int) -> int:
        with self.conn:
            cursor = self.conn.execute("DELETE FROM checks WHERE ts < ?", (before,))
        return cursor.rowcount

    # --- incidents ---

    def open_incident(self, monitor: str) -> Incident | None:
        row = self.conn.execute(
            "SELECT * FROM incidents WHERE monitor = ? AND resolved_at IS NULL"
            " ORDER BY started_at DESC LIMIT 1",
            (monitor,),
        ).fetchone()
        return self._incident(row) if row else None

    def start_incident(self, monitor: str, started_at: int, cause: str | None) -> Incident:
        with self.conn:
            cursor = self.conn.execute(
                "INSERT INTO incidents (monitor, started_at, cause) VALUES (?, ?, ?)",
                (monitor, started_at, cause),
            )
        return Incident(cursor.lastrowid, monitor, started_at, None, cause)

    def resolve_incident(self, incident_id: int, resolved_at: int) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE incidents SET resolved_at = ? WHERE id = ?", (resolved_at, incident_id)
            )

    def incidents_since(self, since: int, monitor: str | None = None) -> list[Incident]:
        query = "SELECT * FROM incidents WHERE (resolved_at IS NULL OR resolved_at >= ?)"
        params: list = [since]
        if monitor:
            query += " AND monitor = ?"
            params.append(monitor)
        rows = self.conn.execute(query + " ORDER BY started_at DESC", params).fetchall()
        return [self._incident(row) for row in rows]

    # --- row mapping ---

    @staticmethod
    def _check(row: sqlite3.Row) -> Check:
        return Check(row["monitor"], row["ts"], bool(row["ok"]), row["status_code"], row["latency_ms"], row["error"])

    @staticmethod
    def _incident(row: sqlite3.Row) -> Incident:
        return Incident(row["id"], row["monitor"], row["started_at"], row["resolved_at"], row["cause"])

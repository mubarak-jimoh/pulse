"""Server-rendered status page and badge. No template engine, no JavaScript."""

from __future__ import annotations

from datetime import UTC, datetime
from html import escape

from .alerts import format_duration

HEADLINES = {
    "up": "All systems operational",
    "degraded": "Some checks are failing",
    "down": "Service disruption",
    "pending": "Waiting for the first checks",
}
LABELS = {"up": "Operational", "degraded": "Degraded", "down": "Down", "pending": "Pending"}

CSS = """
:root{--bg:#f6f7f9;--card:#fff;--text:#14171c;--muted:#667085;--line:#e4e7ec;
--up:#12a150;--degraded:#d98a00;--down:#d92d20;--nodata:#d5d9e0;--pending:#98a2b3}
@media (prefers-color-scheme:dark){:root{--bg:#0d1014;--card:#161a20;--text:#eef1f5;
--muted:#98a2b3;--line:#262c35;--up:#32d17c;--degraded:#f5b041;--down:#f97066;--nodata:#2c333d;--pending:#667085}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:860px;margin:0 auto;padding:40px 16px 64px}
h1{font-size:20px;margin:0 0 20px;font-weight:600}
h2{font-size:15px;margin:36px 0 12px;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.06em}
.banner{padding:20px 24px;border-radius:14px;color:#fff;font-size:20px;font-weight:600;background:var(--pending)}
.banner.up{background:var(--up)}.banner.degraded{background:var(--degraded)}.banner.down{background:var(--down)}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px 24px;margin-top:14px}
.row{display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap}
.name{font-weight:600}.name a{color:inherit;text-decoration:none}.name a:hover{text-decoration:underline}
.state{font-weight:600;font-size:14px}
.state.up{color:var(--up)}.state.degraded{color:var(--degraded)}.state.down{color:var(--down)}.state.pending{color:var(--pending)}
.bars{display:flex;gap:2px;height:34px;margin:14px 0 6px}
.bars i{flex:1;border-radius:2px;background:var(--nodata);min-width:1px}
.bars i.up{background:var(--up)}.bars i.degraded{background:var(--degraded)}.bars i.down{background:var(--down)}
.axis,.meta{display:flex;justify-content:space-between;color:var(--muted);font-size:13px;gap:12px;flex-wrap:wrap}
.meta{margin-top:12px;justify-content:flex-start;gap:20px}
.meta b{color:var(--text);font-weight:600}
.error{color:var(--down);font-size:14px;margin-top:8px}
.incident{padding:12px 0;border-top:1px solid var(--line)}.incident:first-child{border-top:0;padding-top:0}
.incident:last-child{padding-bottom:0}
.incident small,footer{color:var(--muted);font-size:13px}
footer{margin-top:40px;text-align:center}
"""


def _time(ts: int) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%d %b %Y, %H:%M UTC")


def _pct(value: float | None) -> str:
    return "–" if value is None else f"{value:.2f}%"


def _ms(value: float | None) -> str:
    return "–" if value is None else f"{value:.0f} ms"


def _monitor(m: dict) -> str:
    bars = "".join(
        f'<i class="{d["state"]}" title="{datetime.fromtimestamp(d["date"], UTC):%d %b}: '
        f'{"no data" if d["uptime"] is None else _pct(d["uptime"])}"></i>'
        for d in m["days"]
    )
    error = ""
    if m["state"] in ("down", "degraded") and m["last_error"]:
        error = f'<div class="error">{escape(m["last_error"])}</div>'
    return f"""
<section class="card">
  <div class="row">
    <span class="name"><a href="{escape(m["url"], quote=True)}" rel="noopener">{escape(m["name"])}</a></span>
    <span class="state {m["state"]}">{LABELS[m["state"]]}</span>
  </div>
  <div class="bars" role="img" aria-label="Daily uptime for the last {len(m["days"])} days">{bars}</div>
  <div class="axis"><span>{len(m["days"])} days ago</span><span>Today</span></div>
  <div class="meta">
    <span>24h <b>{_pct(m["uptime_24h"])}</b></span>
    <span>7d <b>{_pct(m["uptime_7d"])}</b></span>
    <span>30d <b>{_pct(m["uptime_30d"])}</b></span>
    <span>p50 <b>{_ms(m["p50_ms"])}</b></span>
    <span>p95 <b>{_ms(m["p95_ms"])}</b></span>
  </div>{error}
</section>"""


def _incident(i: dict) -> str:
    if i["resolved_at"] is None:
        when = f"Started {_time(i['started_at'])} · ongoing for {format_duration(i['duration'])}"
    else:
        when = f"{_time(i['started_at'])} · lasted {format_duration(i['duration'])}"
    cause = f" — {escape(i['cause'])}" if i["cause"] else ""
    return f'<div class="incident"><b>{escape(i["monitor"])}</b>{cause}<br><small>{when}</small></div>'


def render(data: dict) -> str:
    monitors = "".join(_monitor(m) for m in data["monitors"])
    if data["incidents"]:
        incidents = "".join(_incident(i) for i in data["incidents"])
    else:
        incidents = '<div class="incident">No incidents in the last 30 days.</div>'
    title = escape(data["title"])
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="60">
<title>{title}</title>
<style>{CSS}</style>
</head>
<body>
<main>
  <h1>{title}</h1>
  <div class="banner {data["state"]}" role="status">{HEADLINES[data["state"]]}</div>
  {monitors}
  <h2>Incidents, last 30 days</h2>
  <section class="card">{incidents}</section>
  <footer>Updated {_time(data["generated_at"])} · Powered by Pulse</footer>
</main>
</body>
</html>"""


def badge_svg(uptime: float | None) -> str:
    if uptime is None:
        value, colour = "no data", "#98a2b3"
    else:
        value = f"{uptime:.2f}%"
        colour = "#12a150" if uptime >= 99.5 else "#d98a00" if uptime >= 95 else "#d92d20"
    right = 14 + len(value) * 7
    width = 52 + right
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="20" role="img" '
        f'aria-label="uptime: {value}"><title>uptime: {value}</title>'
        f'<rect width="{width}" height="20" rx="3" fill="#555"/>'
        f'<rect x="52" width="{right}" height="20" rx="3" fill="{colour}"/>'
        f'<rect x="52" width="4" height="20" fill="{colour}"/>'
        '<g fill="#fff" font-family="Verdana,Geneva,sans-serif" font-size="11" text-anchor="middle">'
        f'<text x="26" y="14">uptime</text><text x="{52 + right / 2:g}" y="14">{value}</text></g></svg>'
    )

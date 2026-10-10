import httpx

from pulse.config import Settings
from pulse.scheduler import Scheduler

from .conftest import NOW, client_returning


def make_scheduler(db, monitor, statuses, webhook=None):
    """A scheduler whose monitored site returns ``statuses`` in order; alerts are collected."""
    alerts = []
    queue = list(statuses)

    def handler(request):
        if request.method == "POST":
            alerts.append(request.content.decode())
            return httpx.Response(200)
        return httpx.Response(queue.pop(0))

    settings = Settings(monitors=[monitor], failure_threshold=2, webhook_url=webhook)
    return Scheduler(settings, db, client_returning(handler)), alerts


async def test_check_once_stores_the_result(db, monitor):
    scheduler, _ = make_scheduler(db, monitor, [200])
    assert await scheduler.check_once(monitor, NOW) is None
    assert db.latest_check("main-site").ok


async def test_alerts_on_down_and_recovery(db, monitor):
    scheduler, alerts = make_scheduler(db, monitor, [500, 500, 500, 200], "https://hooks.example.com/x")
    kinds = []
    for i in range(4):
        transition = await scheduler.check_once(monitor, NOW + i * 60)
        kinds.append(transition.kind if transition else None)

    assert kinds == [None, "opened", None, "resolved"]
    assert len(alerts) == 2
    assert "DOWN: Main site" in alerts[0]
    assert "RECOVERED: Main site is back up after 3m" in alerts[1]


async def test_no_alert_without_webhook(db, monitor):
    scheduler, alerts = make_scheduler(db, monitor, [500, 500])
    await scheduler.check_once(monitor, NOW)
    assert (await scheduler.check_once(monitor, NOW + 60)).kind == "opened"
    assert alerts == []


async def test_start_and_stop_cleans_up_tasks(db, monitor):
    scheduler, _ = make_scheduler(db, monitor, [200] * 5)
    scheduler.start()
    assert len(scheduler._tasks) == 2  # one monitor loop and the prune loop
    await scheduler.stop()
    assert scheduler._tasks == []

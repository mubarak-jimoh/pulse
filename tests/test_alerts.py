import json

import httpx
import pytest

from pulse import alerts
from pulse.db import Incident
from pulse.incidents import Transition

from .conftest import NOW, client_returning


@pytest.mark.parametrize(
    "seconds, text",
    [(5, "5s"), (60, "1m"), (95, "1m 35s"), (3600, "1h"), (3900, "1h 5m"), (90000, "25h")],
)
def test_format_duration(seconds, text):
    assert alerts.format_duration(seconds) == text


def test_down_message_includes_cause():
    transition = Transition("opened", Incident(1, "api", NOW, None, "could not connect"))
    message = alerts.build_message("API", "https://api.example.com", transition)
    assert message == "DOWN: API is not responding (could not connect). https://api.example.com"


def test_recovered_message_includes_downtime():
    transition = Transition("resolved", Incident(1, "api", NOW, NOW + 150, None))
    assert "back up after 2m 30s" in alerts.build_message("API", "https://x.com", transition)


async def test_notify_posts_slack_and_discord_fields():
    sent = {}

    def handler(request):
        sent.update(json.loads(request.content))
        return httpx.Response(204)

    assert await alerts.notify(client_returning(handler), "https://hooks.example.com/x", "hello")
    assert sent == {"text": "hello", "content": "hello"}


async def test_failed_webhook_does_not_raise():
    client = client_returning(lambda request: httpx.Response(500))
    assert await alerts.notify(client, "https://hooks.example.com/x", "hello") is False

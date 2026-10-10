import pytest

from pulse import config
from pulse.config import ConfigError


def test_parses_monitors_and_defaults():
    settings = config.parse({"monitor": [{"name": "Site", "url": "https://example.com"}]})
    monitor = settings.monitors[0]
    assert (monitor.interval, monitor.timeout, monitor.expect_status) == (60, 10.0, 200)
    assert settings.failure_threshold == 2
    assert settings.webhook_url is None


def test_slug_is_url_safe():
    settings = config.parse({"monitor": [{"name": "My API (v2)", "url": "https://example.com"}]})
    assert settings.monitors[0].slug == "my-api--v2"


def test_loads_from_file(tmp_path):
    path = tmp_path / "monitors.toml"
    path.write_text('title = "Status"\n[[monitor]]\nname = "Site"\nurl = "https://example.com"\ninterval = 30\n')
    settings = config.load(path)
    assert settings.title == "Status"
    assert settings.monitors[0].interval == 30


def test_missing_file():
    with pytest.raises(ConfigError, match="not found"):
        config.load("does-not-exist.toml")


@pytest.mark.parametrize(
    "data, message",
    [
        ({}, "no monitors"),
        ({"monitor": [{"url": "https://example.com"}]}, "missing 'name'"),
        ({"monitor": [{"name": "Site"}]}, "missing 'url'"),
        ({"monitor": [{"name": "Site", "url": "ftp://example.com"}]}, "invalid url"),
        ({"monitor": [{"name": "Site", "url": "example.com"}]}, "invalid url"),
        ({"monitor": [{"name": "Site", "url": "https://example.com", "interval": 1}]}, "at least 5"),
        ({"monitor": [{"name": "Site", "url": "https://example.com", "timeout": 90}]}, "timeout"),
        ({"failure_threshold": 0, "monitor": [{"name": "Site", "url": "https://example.com"}]}, "failure_threshold"),
    ],
)
def test_rejects_bad_config(data, message):
    with pytest.raises(ConfigError, match=message):
        config.parse(data)


def test_rejects_duplicate_names():
    monitors = [{"name": "Site", "url": "https://a.com"}, {"name": "site", "url": "https://b.com"}]
    with pytest.raises(ConfigError, match="unique"):
        config.parse({"monitor": monitors})

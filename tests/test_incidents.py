from pulse import incidents

from .conftest import NOW, make_check


def feed(db, pattern, threshold=2, start=NOW, step=60):
    """Record a run of checks ('.' = pass, 'x' = fail) and return the transitions."""
    out = []
    for i, char in enumerate(pattern):
        out.append(incidents.record(db, make_check(ok=char == ".", ts=start + i * step), threshold))
    return out


def test_passing_checks_open_nothing(db):
    assert feed(db, "....") == [None] * 4
    assert db.open_incident("main-site") is None


def test_single_failure_is_ignored(db):
    assert feed(db, ".x.") == [None, None, None]
    assert db.incidents_since(0) == []


def test_incident_opens_after_threshold(db):
    transitions = feed(db, ".xx")
    assert transitions[:2] == [None, None]
    assert transitions[2].kind == "opened"
    assert transitions[2].incident.cause == "expected status 200, got 500"


def test_incident_starts_at_first_failure(db):
    opened = feed(db, ".xxx", threshold=3)[3]
    assert opened.incident.started_at == NOW + 60


def test_no_duplicate_incident_while_down(db):
    transitions = feed(db, "xxxxx")
    assert [t.kind if t else None for t in transitions] == [None, "opened", None, None, None]
    assert len(db.incidents_since(0)) == 1


def test_recovery_resolves_incident(db):
    resolved = feed(db, "xxx.")[3]
    assert resolved.kind == "resolved"
    assert resolved.incident.duration(NOW) == 180
    assert db.open_incident("main-site") is None


def test_threshold_of_one_opens_immediately(db):
    assert feed(db, "x", threshold=1)[0].kind == "opened"


def test_flapping_creates_separate_incidents(db):
    feed(db, "xx.xx.")
    assert len(db.incidents_since(0)) == 2


def test_monitors_are_independent(db):
    incidents.record(db, make_check(ok=False, ts=NOW, monitor="a"))
    assert incidents.record(db, make_check(ok=False, ts=NOW + 60, monitor="b")) is None
    assert incidents.record(db, make_check(ok=False, ts=NOW + 120, monitor="a")).kind == "opened"
    assert db.open_incident("b") is None

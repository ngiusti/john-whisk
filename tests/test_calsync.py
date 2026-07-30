"""Read-only iCal calendar sync. Network mocked; DB isolated."""
import datetime

from john_whisk import config, settings, calsync, mealplan

_BEFORE = datetime.datetime(2026, 7, 1)      # cutoff-anchor before the sample dates

SAMPLE_ICS = """BEGIN:VCALENDAR
BEGIN:VEVENT
UID:abc-1
DTSTART;VALUE=DATE:20260717
SUMMARY:Team dinner
END:VEVENT
BEGIN:VEVENT
UID:abc-2
DTSTART:20260718T180000Z
SUMMARY:Movie night
END:VEVENT
END:VCALENDAR
"""


def _fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "p.db"))
    settings.set("online_enabled", "1")


def test_parse_ics():
    events = calsync.parse_ics(SAMPLE_ICS)
    assert {"date": "2026-07-17", "description": "Team dinner"}.items() <= events[0].items()
    assert events[1]["date"] == "2026-07-18" and events[1]["description"] == "Movie night"


def test_sync_replaces_cache(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    settings.set("ical_url", "http://cal.example/x.ics")
    monkeypatch.setattr(calsync.net, "get_text", lambda *a, **k: SAMPLE_ICS)
    assert calsync.sync(now=_BEFORE) == 2
    assert calsync.events_for("2026-07-17") == ["Team dinner"]
    # a re-sync with fewer events replaces (doesn't append)
    monkeypatch.setattr(calsync.net, "get_text", lambda *a, **k:
                        "BEGIN:VEVENT\nDTSTART:20260720\nSUMMARY:Solo\nEND:VEVENT")
    assert calsync.sync(now=_BEFORE) == 1
    assert calsync.events_for("2026-07-17") == []


def test_sync_drops_past_events(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    settings.set("ical_url", "http://cal.example/x.ics")
    ics = ("BEGIN:VEVENT\nDTSTART:20200101\nSUMMARY:Old\nEND:VEVENT\n"
           "BEGIN:VEVENT\nDTSTART:20260717\nSUMMARY:Future\nEND:VEVENT")
    monkeypatch.setattr(calsync.net, "get_text", lambda *a, **k: ics)
    assert calsync.sync(now=_BEFORE) == 1              # only the future event kept
    assert calsync.events_for("2020-01-01") == []
    assert calsync.events_for("2026-07-17") == ["Future"]


def test_sync_none_without_url(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    assert calsync.sync() is None


def test_synced_events_merge_into_upcoming(tmp_path, monkeypatch):
    import datetime
    _fresh(tmp_path, monkeypatch)
    settings.set("ical_url", "http://cal.example/x.ics")
    monkeypatch.setattr(calsync.net, "get_text", lambda *a, **k: SAMPLE_ICS)
    now = datetime.datetime(2026, 7, 15, 12, 0, 0)
    u = mealplan.upcoming(now, days=7)      # triggers maybe_sync
    assert any(e["description"] == "Team dinner" for e in u["events"])


def test_router_sync_calendar():
    from john_whisk import router
    assert router.classify("sync my calendar") == "calendar_query"

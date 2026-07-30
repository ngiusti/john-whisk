"""Google Calendar write. The Calendar service is mocked (no real API/OAuth)."""
import datetime

from john_whisk import calwrite


class _FakeService:
    def __init__(self, sink):
        self._sink = sink

    def events(self):
        svc = self

        class _E:
            def insert(self, **kw):
                svc._sink.update(kw)

                class _Req:
                    def execute(self_):
                        return {"htmlLink": "http://cal/x"}
                return _Req()
        return _E()


def test_create_event_timed(monkeypatch):
    sink = {}
    monkeypatch.setattr(calwrite, "_service", lambda: _FakeService(sink))
    r = calwrite.create_event("Dentist", datetime.datetime(2026, 8, 20, 16, 0))
    assert r["ok"] and sink["calendarId"] == "primary"
    body = sink["body"]
    assert body["summary"] == "Dentist"
    assert body["start"]["dateTime"].startswith("2026-08-20T16:00")
    assert body["end"]["dateTime"].startswith("2026-08-20T17:00")     # +1h default
    assert "timeZone" in body["start"]


def test_create_event_all_day(monkeypatch):
    sink = {}
    monkeypatch.setattr(calwrite, "_service", lambda: _FakeService(sink))
    r = calwrite.create_event("Trip", datetime.date(2026, 8, 20), all_day=True)
    assert r["ok"]
    body = sink["body"]
    assert body["start"]["date"] == "2026-08-20" and body["end"]["date"] == "2026-08-21"


def test_create_event_no_service_returns_none(monkeypatch):
    monkeypatch.setattr(calwrite, "_service", lambda: None)
    assert calwrite.create_event("x", datetime.datetime(2026, 8, 20, 16, 0)) is None


class _FakeSvc2:
    def __init__(self, items=None, sink=None):
        self._items = items or []
        self.sink = sink if sink is not None else {}

    def events(self):
        svc = self

        class _E:
            def list(self, **kw):
                return type("R", (), {"execute": lambda s: {"items": svc._items}})()

            def delete(self, **kw):
                svc.sink["deleted"] = kw.get("eventId")
                return type("R", (), {"execute": lambda s: {}})()

            def patch(self, **kw):
                svc.sink["patched"] = (kw.get("eventId"), kw.get("body"))
                return type("R", (), {"execute": lambda s: {}})()
        return _E()


def test_list_events(monkeypatch):
    items = [{"id": "a", "summary": "Dentist",
              "start": {"dateTime": "2026-07-31T12:00:00-07:00"}}]
    monkeypatch.setattr(calwrite, "_service", lambda: _FakeSvc2(items=items))
    evs = calwrite.list_events()
    assert evs[0]["id"] == "a" and evs[0]["summary"] == "Dentist"
    assert evs[0]["start"].startswith("2026-07-31")


def test_delete_and_update(monkeypatch):
    sink = {}
    monkeypatch.setattr(calwrite, "_service", lambda: _FakeSvc2(sink=sink))
    assert calwrite.delete_event("xyz") is True and sink["deleted"] == "xyz"
    assert calwrite.update_summary("xyz", "New") is True
    assert sink["patched"] == ("xyz", {"summary": "New"})


def test_ops_none_without_service(monkeypatch):
    monkeypatch.setattr(calwrite, "_service", lambda: None)
    assert calwrite.list_events() is None
    assert calwrite.delete_event("x") is False
    assert calwrite.update_summary("x", "y") is False

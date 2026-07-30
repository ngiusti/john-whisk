"""Read-only iCal calendar sync. Fetches a private .ics URL when online, parses
VEVENTs (minimal: date + summary), caches them locally, and reads offline. No
OAuth, no extra deps. Manual meal-plan events are untouched — a sync only
replaces the iCal set."""
import contextlib
import datetime
import re
import sqlite3

from john_whisk import config, net, settings

_SYNC_FRESH_S = 3600
_VEVENT = re.compile(r"BEGIN:VEVENT(.*?)END:VEVENT", re.S)


def _conn():
    return sqlite3.connect(config.DB_PATH)


def init_db():
    with contextlib.closing(_conn()) as c:
        c.execute("CREATE TABLE IF NOT EXISTS ical_events ("
                  "id INTEGER PRIMARY KEY, event_date TEXT NOT NULL, "
                  "description TEXT, uid TEXT, synced_at TEXT NOT NULL)")
        c.commit()


def parse_ics(text):
    """Minimal VEVENT extraction: per event, the DTSTART date + SUMMARY.
    Returns [{date: 'YYYY-MM-DD', description, uid}]. Ignores recurrence/TZ."""
    out = []
    for block in _VEVENT.findall(text or ""):
        dt = re.search(r"DTSTART[^:\n]*:(\d{8})", block)
        if not dt:
            continue
        raw = dt.group(1)
        iso = f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"
        summ = re.search(r"SUMMARY:(.+)", block)
        uid = re.search(r"UID:(.+)", block)
        out.append({"date": iso,
                    "description": (summ.group(1).strip().rstrip("\r") if summ else "event"),
                    "uid": (uid.group(1).strip().rstrip("\r") if uid else "")})
    return out


def sync(now=None):
    """Fetch + parse the iCal URL and replace the cache with today-and-future
    events only (calendars export years of history). Returns event count, or
    None if no URL / offline / unreachable."""
    url = settings.get("ical_url")
    if not url:
        return None
    text = net.get_text(url)
    if text is None:
        return None
    cutoff = ((now or datetime.datetime.now()).date() - datetime.timedelta(days=1)).isoformat()
    events = [e for e in parse_ics(text) if e["date"] >= cutoff]
    init_db()
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    with contextlib.closing(_conn()) as c:
        c.execute("DELETE FROM ical_events")
        for e in events:
            c.execute("INSERT INTO ical_events (event_date, description, uid, synced_at) "
                      "VALUES (?, ?, ?, ?)", (e["date"], e["description"], e["uid"], ts))
        c.commit()
    settings.set("ical_last_sync", ts)
    return len(events)


def _stale(now=None):
    now = now or datetime.datetime.now()
    ts = settings.get("ical_last_sync")
    if not ts:
        return True
    try:
        return (now - datetime.datetime.fromisoformat(ts)).total_seconds() > _SYNC_FRESH_S
    except (ValueError, TypeError):
        return True


def maybe_sync(now=None):
    """Sync only if configured, online, and the cache is stale. Safe no-op
    otherwise (keeps reads off the network when possible)."""
    if settings.get("ical_url") and net.online() and _stale(now):
        sync(now)


def events_for(date):
    init_db()
    with contextlib.closing(_conn()) as c:
        return [r[0] for r in c.execute(
            "SELECT description FROM ical_events WHERE event_date = ? ORDER BY id",
            (date,)).fetchall()]


def answer_sync():
    n = sync()
    if n is None:
        return ("I couldn't reach your calendar. Add or check the iCal link in "
                "settings, or you may be offline.")
    return f"Synced your calendar — {n} event{'s' if n != 1 else ''}."

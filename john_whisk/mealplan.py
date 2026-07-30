"""Meal-planning calendar (offline). Schedule dishes onto dates and ask what's
planned. Also holds personal events + an "upcoming" look-ahead (Phase 2). Dates
are ISO YYYY-MM-DD strings in the pantry DB. `now` is injected for testing."""
import contextlib
import datetime
import re
import sqlite3

from john_whisk import config

_WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
             "friday": 4, "saturday": 5, "sunday": 6}
_MONTHS = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5,
           "june": 6, "july": 7, "august": 8, "september": 9, "october": 10,
           "november": 11, "december": 12}

_DAY_HINT = re.compile(
    r"\b(today|tonight|tomorrow|this week|next week|this month|next month|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"january|february|march|april|may|june|july|august|september|october|"
    r"november|december|in \d+ days?|\d{1,2}(?:st|nd|rd|th))\b")

# Cut a dish phrase at the first date-connective word.
_LEAD = re.compile(r"^\s*(please\s+)?(plan|schedule|put|add|set up|pencil in)\b\s*")
_CUT = re.compile(
    r"\b(for|on|to|this|next|tomorrow|tonight|today|in\s+\d+\s+days?|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"january|february|march|april|may|june|july|august|september|october|"
    r"november|december|\d{1,2}(?:st|nd|rd|th))\b")


def _now():
    return datetime.datetime.now()


def _norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", (s or "").lower())).strip()


def _join(parts):
    parts = list(parts)
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return parts[0] + " and " + parts[1]
    return ", ".join(parts[:-1]) + ", and " + parts[-1]


def mentions_day(text):
    """True if the text names a day/date — used so 'what am I making Friday'
    routes to the calendar instead of the live-kitchen summary."""
    return bool(_DAY_HINT.search((text or "").lower()))


def parse_date(text, now=None):
    """A date from common spoken forms, or None. See the spec for supported
    phrasings."""
    now = now or _now()
    today = now.date()
    t = _norm(text)
    if not t:
        return None
    if "today" in t or "tonight" in t:
        return today
    if "tomorrow" in t:
        return today + datetime.timedelta(days=1)
    m = re.search(r"in (\d+) days?", t)
    if m:
        return today + datetime.timedelta(days=int(m.group(1)))
    for wd, idx in _WEEKDAYS.items():
        if wd in t:
            base = (idx - today.weekday()) % 7
            if "next" in t:
                base += 7
            return today + datetime.timedelta(days=base)
    for mon, mi in _MONTHS.items():
        if mon in t:
            dm = re.search(r"(\d{1,2})", t)
            if dm:
                try:
                    d = datetime.date(today.year, mi, int(dm.group(1)))
                except ValueError:
                    return None
                return d if d >= today else datetime.date(today.year + 1, mi, int(dm.group(1)))
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)\b", t)
    if m:
        day = int(m.group(1))
        try:
            d = datetime.date(today.year, today.month, day)
        except ValueError:
            return None
        if d < today:
            nm, ny = (today.month % 12 + 1), today.year + (1 if today.month == 12 else 0)
            try:
                d = datetime.date(ny, nm, day)
            except ValueError:
                return None
        return d
    return None


def _friendly(date, now=None):
    now = now or _now()
    today = now.date()
    if date == today:
        return "today"
    if date == today + datetime.timedelta(days=1):
        return "tomorrow"
    if 0 < (date - today).days < 7:
        return date.strftime("%A")
    return f"{date.strftime('%B')} {date.day}"


def _extract_dish(text):
    t = _LEAD.sub("", (text or "").strip())
    return _CUT.split(t, maxsplit=1)[0].strip(" ,.")


# --- store ----------------------------------------------------------------

def _conn():
    return sqlite3.connect(config.DB_PATH)


def init_db():
    with contextlib.closing(_conn()) as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS meal_plan (
                   id        INTEGER PRIMARY KEY,
                   plan_date TEXT NOT NULL,
                   dish      TEXT NOT NULL,
                   added_at  TEXT NOT NULL)"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS events (
                   id          INTEGER PRIMARY KEY,
                   event_date  TEXT NOT NULL,
                   description TEXT NOT NULL,
                   added_at    TEXT NOT NULL)"""
        )
        c.commit()


def add_plan(date, dish):
    init_db()
    now = datetime.datetime.now().isoformat(timespec="seconds")
    with contextlib.closing(_conn()) as c:
        c.execute("INSERT INTO meal_plan (plan_date, dish, added_at) VALUES (?, ?, ?)",
                  (date, dish, now))
        c.commit()


def plan_for(date):
    init_db()
    with contextlib.closing(_conn()) as c:
        return [r[0] for r in c.execute(
            "SELECT dish FROM meal_plan WHERE plan_date = ? ORDER BY id", (date,)).fetchall()]


def plan_entries(date):
    """(id, dish) rows for a date (for the dashboard)."""
    init_db()
    with contextlib.closing(_conn()) as c:
        return [{"id": r[0], "dish": r[1]} for r in c.execute(
            "SELECT id, dish FROM meal_plan WHERE plan_date = ? ORDER BY id", (date,)).fetchall()]


def remove_plan(entry_id):
    init_db()
    with contextlib.closing(_conn()) as c:
        c.execute("DELETE FROM meal_plan WHERE id = ?", (entry_id,))
        c.commit()


def clear_date(date):
    init_db()
    with contextlib.closing(_conn()) as c:
        c.execute("DELETE FROM meal_plan WHERE plan_date = ?", (date,))
        c.commit()


def week(start=None, days=7):
    """Ordered day dicts for a window: {date, weekday, dishes}."""
    start = start or _now().date()
    out = []
    for i in range(days):
        d = start + datetime.timedelta(days=i)
        out.append({"date": d.isoformat(), "weekday": d.strftime("%A"),
                    "dishes": plan_for(d.isoformat())})
    return out


def week_entries(start=None, days=7):
    """Like week() but with removable entry ids, for the dashboard:
    {date, weekday, entries:[{id, dish}]}."""
    start = start or _now().date()
    out = []
    for i in range(days):
        d = start + datetime.timedelta(days=i)
        out.append({"date": d.isoformat(), "weekday": d.strftime("%A"),
                    "entries": plan_entries(d.isoformat())})
    return out


# --- voice ----------------------------------------------------------------

def handle_set(text, now=None):
    now = now or _now()
    date = parse_date(text, now)
    if date is None:
        return "Which day should I plan that for?"
    dish = _extract_dish(text)
    if not dish:
        return "What would you like to plan?"
    add_plan(date.isoformat(), dish)
    return f"Planned {dish} for {_friendly(date, now)}."


def _answer_range(now, days, label):
    planned = [d for d in week(now.date(), days) if d["dishes"]]
    if not planned:
        return f"You have nothing planned {label}."
    parts = [f"{d['weekday']}, {_join(d['dishes'])}" for d in planned]
    return f"Here's {label}: " + "; ".join(parts) + "."


def handle_query(text, now=None):
    now = now or _now()
    t = _norm(text)
    if "week" in t:
        return _answer_range(now, 7, "this week")
    if "month" in t:
        return _answer_range(now, 30, "this month")
    date = parse_date(text, now) or now.date()
    dishes = plan_for(date.isoformat())
    if not dishes:
        return f"You have nothing planned for {_friendly(date, now)}."
    return f"For {_friendly(date, now)}, you're making " + _join(dishes) + "."

"""Pantry expiration alerts. Estimates freshness from each item's logged
`added_at` (re-buying refreshes it) plus a per-category shelf-life table —
offline, no extra data. A helpful nudge, not a food-safety guarantee."""
import contextlib
import datetime
import sqlite3

from john_whisk import config

# Rough days a category keeps once logged. Conservative; a nudge, not a guarantee.
SHELF_LIFE_DAYS = {
    "vegetable": 7, "fruit": 7, "herb": 5, "dairy": 14, "protein": 4,
    "sauce": 30, "condiment": 90, "grain": 180, "pasta": 365, "spice": 730,
    "baking": 365, "oil": 365, "legume": 365, "nuts": 180, "beverage": 30,
    "other": 21,
}
DEFAULT_SHELF_LIFE = 21
SOON_DAYS = 2          # within this many days of the estimate -> "use it soon"


def _conn():
    return sqlite3.connect(config.DB_PATH)


def _now():
    return datetime.datetime.now()


def _join(parts):
    parts = list(parts)
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return parts[0] + " and " + parts[1]
    return ", ".join(parts[:-1]) + ", and " + parts[-1]


def shelf_life(category):
    return SHELF_LIFE_DAYS.get((category or "").lower(), DEFAULT_SHELF_LIFE)


def _age_days(added_at, now):
    try:
        return (now - datetime.datetime.fromisoformat(added_at)).days
    except (ValueError, TypeError):
        return 0


def status(item, now=None):
    """{name, category, age_days, shelf_life, days_left, status} for one pantry
    item dict {name, category, added_at}. status is expired | soon | fresh."""
    now = now or _now()
    sl = shelf_life(item.get("category"))
    age = _age_days(item.get("added_at"), now)
    left = sl - age
    st = "expired" if left < 0 else ("soon" if left <= SOON_DAYS else "fresh")
    return {"name": item.get("name"), "category": item.get("category"),
            "age_days": age, "shelf_life": sl, "days_left": left, "status": st}


def _items():
    from john_whisk import db
    db.init_db()
    with contextlib.closing(_conn()) as c:
        rows = c.execute(
            "SELECT name, category, added_at FROM inventory ORDER BY added_at").fetchall()
    return [{"name": r[0], "category": r[1], "added_at": r[2]} for r in rows]


def annotate(now=None):
    """Expiration status for every pantry item (for the dashboard)."""
    now = now or _now()
    return [status(it, now) for it in _items()]


def expiring(within_days=SOON_DAYS, now=None):
    """Items that are expired or within `within_days` of their estimate,
    oldest/most-overdue first."""
    now = now or _now()
    hits = [s for s in annotate(now) if s["days_left"] <= within_days]
    return sorted(hits, key=lambda s: s["days_left"])


def answer_expiring(now=None):
    """Spoken 'what's going bad' — expired items and ones to use soon."""
    exp = expiring(now=now)
    if not exp:
        return "Nothing in your pantry is about to go bad."
    past = [e["name"] for e in exp if e["status"] == "expired"]
    soon = [e["name"] for e in exp if e["status"] == "soon"]
    parts = []
    if past:
        parts.append(f"{_join(past)} {'is' if len(past) == 1 else 'are'} likely past their prime")
    if soon:
        parts.append(f"{_join(soon)} should be used soon")
    return "Heads up — " + "; ".join(parts) + ". Give them a check before using."

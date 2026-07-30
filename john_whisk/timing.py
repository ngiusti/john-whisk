"""Time-based recipe filtering. Stored recipes carry no structured times, so we
ESTIMATE minutes from step count + slow-step keywords (offline), cache the
estimate on the recipe row, and answer "what can I make in 20 minutes"."""
import contextlib
import json
import re
import sqlite3

from john_whisk import config, recipes

# Extra minutes when a step mentions a slow technique (counted once per recipe).
_SLOW = {"bake": 25, "roast": 40, "simmer": 20, "marinate": 60, "marinade": 60,
         "slow cook": 240, "slow-cook": 240, "overnight": 480, "refrigerate": 30,
         "chill": 30, "rest": 15, "proof": 90, "rise": 90, "braise": 90,
         "boil": 10, "soak": 60, "freeze": 120}
_BASE_MIN = 5           # prep/setup floor
_PER_STEP = 4           # minutes per step
_CAP = 600


def _conn():
    return sqlite3.connect(config.RECIPES_DB_PATH)


def _join(parts):
    parts = list(parts)
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return parts[0] + " and " + parts[1]
    return ", ".join(parts[:-1]) + ", and " + parts[-1]


def estimate_minutes(recipe):
    """Rough total minutes for a recipe from its steps. A heuristic estimate,
    not a stated time."""
    steps = recipe.get("steps") or []
    mins = _BASE_MIN + _PER_STEP * len(steps)
    text = " ".join(steps).lower()
    for kw, add in _SLOW.items():
        if kw in text:
            mins += add
    return min(mins, _CAP)


def quick_recipes(max_minutes, limit=8):
    """Stored recipes whose estimated time is <= max_minutes, fastest first.
    Estimates are computed once and cached on the recipe row."""
    recipes.init_db()
    with contextlib.closing(_conn()) as c:
        rows = c.execute("SELECT id, title, steps, minutes FROM recipes").fetchall()
        out = []
        for rid, title, steps_json, minutes in rows:
            if minutes is None:
                minutes = estimate_minutes({"steps": json.loads(steps_json or "[]")})
                c.execute("UPDATE recipes SET minutes = ? WHERE id = ?", (minutes, rid))
            if minutes <= max_minutes:
                out.append({"title": title, "minutes": int(minutes)})
        c.commit()
    out.sort(key=lambda r: r["minutes"])
    return out[:limit]


def parse_minutes(text):
    """A time budget in minutes from speech. Defaults to 30 for a vague ask."""
    t = text.lower()
    if "hour" in t:
        m = re.search(r"(\d+(?:\.\d+)?)\s*hour", t)
        if m:
            return int(float(m.group(1)) * 60)
        if "half an hour" in t:
            return 30
        return 60
    m = re.search(r"(\d+)\s*(?:min|minute)", t)
    if m:
        return int(m.group(1))
    if "quick" in t or "hurry" in t or "fast" in t:
        return 20
    m2 = re.search(r"\b(\d+)\b", t)
    return int(m2.group(1)) if m2 else 30


def answer_quick(text):
    """Spoken 'what can I make in X minutes'."""
    budget = parse_minutes(text)
    hits = quick_recipes(budget)
    if not hits:
        return f"I couldn't find a stored recipe under about {budget} minutes."
    names = [h["title"] for h in hits[:4]]
    return f"In about {budget} minutes you could make " + _join(names) + "."

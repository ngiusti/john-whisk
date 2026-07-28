"""Kitchen equipment inventory. Declare notable appliances once; recipes that
need a tool you don't have warn (cook/plan), and suggestions favor makeable
recipes. Keyword detection from recipe steps (a hint, not exact); basics
(stovetop, pan, pot, knife, bowl) are assumed on hand."""
import sqlite3
import contextlib
import datetime
import re

from john_whisk import config

# notable equipment -> step keywords that imply it (phrases matched as
# substrings, single words whole-word), tuned to limit false positives.
RULES = {
    "blender": ["blend", "blender", "puree", "smoothie"],
    "food processor": ["food processor"],
    "stand mixer": ["stand mixer", "electric mixer"],
    "slow cooker": ["slow cooker", "crockpot", "crock pot"],
    "air fryer": ["air fry", "air fryer", "air-fry"],
    "grill": ["on the grill", "grill the", "barbecue", "bbq"],
    "oven": ["in the oven", "bake", "baked", "roast", "roasted", "broil"],
    "microwave": ["microwave"],
    "pressure cooker": ["pressure cook", "pressure cooker", "instant pot"],
    "waffle iron": ["waffle iron", "waffle maker"],
}

# spoken alias -> canonical equipment name
_ALIASES = {
    "crockpot": "slow cooker", "crock pot": "slow cooker",
    "instant pot": "pressure cooker", "instapot": "pressure cooker",
    "airfryer": "air fryer", "waffle maker": "waffle iron",
    "mixer": "stand mixer", "processor": "food processor",
}


def _conn():
    return sqlite3.connect(config.DB_PATH)


def _norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", (s or "").lower())).strip()


def _join(parts):
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return parts[0] + " and " + parts[1]
    return ", ".join(parts[:-1]) + ", and " + parts[-1]


def _a(word):
    return ("an " if word[:1] in "aeiou" else "a ") + word


# --- store ----------------------------------------------------------------

def init_db():
    with contextlib.closing(_conn()) as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS equipment (
                   id       INTEGER PRIMARY KEY,
                   item     TEXT NOT NULL UNIQUE,
                   added_at TEXT NOT NULL)"""
        )
        c.commit()


def add(names):
    if isinstance(names, str):
        names = [names]
    init_db()
    now = datetime.datetime.now().isoformat(timespec="seconds")
    with contextlib.closing(_conn()) as c:
        for n in names:
            n = str(n).strip().lower()
            if n:
                c.execute("INSERT OR IGNORE INTO equipment (item, added_at) VALUES (?, ?)",
                          (n, now))
        c.commit()


def remove(names):
    if isinstance(names, str):
        names = [names]
    init_db()
    with contextlib.closing(_conn()) as c:
        for n in names:
            c.execute("DELETE FROM equipment WHERE item = ?", (str(n).strip().lower(),))
        c.commit()


def owned():
    init_db()
    with contextlib.closing(_conn()) as c:
        return [r[0] for r in c.execute(
            "SELECT item FROM equipment ORDER BY added_at, id").fetchall()]


def clear():
    init_db()
    with contextlib.closing(_conn()) as c:
        c.execute("DELETE FROM equipment")
        c.commit()


# --- detection ------------------------------------------------------------

def _canonical(text):
    t = _norm(text)
    for alias, canon in sorted(_ALIASES.items(), key=lambda kv: -len(kv[0])):
        if alias in t:
            return canon
    for name in sorted(RULES, key=len, reverse=True):
        if name in t:
            return name
    return None


def _all_mentioned(text):
    """Every notable equipment named in the text (for multi-add utterances)."""
    t = _norm(text)
    found = []
    for alias, canon in _ALIASES.items():
        if alias in t and canon not in found:
            found.append(canon)
    for name in RULES:
        if name in t and name not in found:
            found.append(name)
    return found


def required(recipe):
    """The notable equipment a recipe's steps imply."""
    text = _norm(" . ".join(recipe.get("steps", [])))
    words = set(text.split())
    out = set()
    for equip, kws in RULES.items():
        for kw in kws:
            if (kw in text) if " " in kw else (kw in words):
                out.add(equip)
                break
    return out


def missing(recipe):
    own = set(owned())
    return [e for e in sorted(required(recipe)) if e not in own]


def warning(recipe):
    m = missing(recipe)
    if not m:
        return ""
    return (f"Heads up — {recipe.get('title', 'this recipe')} needs "
            + _join([_a(e) for e in m])
            + ", which you haven't listed in your equipment.")


def prompt_clause():
    o = owned()
    if not o:
        return ""
    return f"I have this kitchen equipment: {', '.join(o)}. Prefer recipes I can make with it. "


# --- voice commands -------------------------------------------------------

def answer_list():
    o = owned()
    if not o:
        return "You haven't listed any kitchen equipment yet."
    return "You have " + _join([_a(e) for e in o]) + "."


def set_from_text(text):
    items = _all_mentioned(text)
    if items:
        add(items)
    return items


def remove_from_text(text):
    items = _all_mentioned(text)
    if items:
        remove(items)
    return items


def handle(text):
    t = _norm(text)
    if "clear" in t or "remove all" in t:
        clear()
        return "Okay, I've cleared your equipment list."
    if "don t have" in t or "dont have" in t or "do not have" in t or "remove" in t or "got rid" in t:
        items = remove_from_text(text)
        if items:
            return "Okay, I've removed " + _join(items) + " from your equipment."
        return "Which piece of equipment should I remove?"
    if ("what" in t or "list" in t or "my equipment" in t
            or "do i have" in t or "do you have" in t or "have i got" in t):
        return answer_list()
    items = set_from_text(text)
    if items:
        return "Got it — I've noted your " + _join(items) + "."
    return "I'm not sure which piece of equipment you mean."

"""Grocery list + meal planning: "I would like to make X" finds the recipe,
checks it against the pantry, and adds the missing ingredients to a persistent
grocery list. Deterministic where it can be (matching, list ops); the LLM is
only used as a recipe fallback via recipes.resolve."""
import sqlite3
import contextlib
import datetime
import re

from john_whisk import config, db, recipes

_STAPLES = {"salt", "pepper", "water", "oil"}


def _conn():
    return sqlite3.connect(config.DB_PATH)


def _norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", (s or "").lower())).strip()


def _singular(w):
    w = w.strip().lower()
    if len(w) > 3 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 2 and w.endswith("es"):
        return w[:-2]
    if len(w) > 1 and w.endswith("s"):
        return w[:-1]
    return w


def _words(s):
    return {_singular(w) for w in _norm(s).split() if w}


def _join(parts):
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return parts[0] + " and " + parts[1]
    return ", ".join(parts[:-1]) + ", and " + parts[-1]


# --- store ----------------------------------------------------------------

def init_db():
    with contextlib.closing(_conn()) as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS grocery (
                   id        INTEGER PRIMARY KEY,
                   item      TEXT NOT NULL,
                   item_norm TEXT NOT NULL,
                   added_at  TEXT NOT NULL)"""
        )
        c.commit()


def add(items):
    """Add item(s) to the grocery list, deduped by normalized text. Returns the
    items actually added."""
    if isinstance(items, str):
        items = [items]
    init_db()
    now = datetime.datetime.now().isoformat(timespec="seconds")
    added = []
    with contextlib.closing(_conn()) as c:
        for it in items:
            it = str(it).strip()
            n = _norm(it)
            if not n:
                continue
            if c.execute("SELECT 1 FROM grocery WHERE item_norm = ?", (n,)).fetchone():
                continue
            c.execute("INSERT INTO grocery (item, item_norm, added_at) VALUES (?, ?, ?)",
                      (it, n, now))
            added.append(it)
        c.commit()
    return added


def items():
    init_db()
    with contextlib.closing(_conn()) as c:
        return [r[0] for r in c.execute(
            "SELECT item FROM grocery ORDER BY added_at, id").fetchall()]


def remove(names):
    if isinstance(names, str):
        names = [names]
    init_db()
    removed = []
    with contextlib.closing(_conn()) as c:
        for nm in names:
            n = _norm(nm)
            if not n:
                continue
            for rid, item, inorm in c.execute("SELECT id, item, item_norm FROM grocery").fetchall():
                if n == inorm or n in inorm or inorm in n:
                    c.execute("DELETE FROM grocery WHERE id = ?", (rid,))
                    removed.append(item)
                    break
        c.commit()
    return removed


def clear():
    init_db()
    with contextlib.closing(_conn()) as c:
        c.execute("DELETE FROM grocery")
        c.commit()


# --- missing-ingredient detection -----------------------------------------

def _missing(ingredients_str, pantry):
    """Return the recipe ingredients not covered by the pantry (skipping basic
    staples). An ingredient is covered if a pantry item name matches a whole
    word in it (singular/plural tolerant)."""
    pantry_words = set()
    for p in pantry:
        pantry_words |= _words(p["name"])
    missing = []
    for ing in ingredients_str.split(","):
        ing = ing.strip()
        if not ing:
            continue
        iw = _words(ing)
        if iw & _STAPLES:            # basic staple, assume on hand
            continue
        if iw & pantry_words:        # covered by something in the pantry
            continue
        missing.append(ing)
    return missing


# --- planning + voice commands --------------------------------------------

def plan_meal(dish):
    """Find the recipe for a dish, add its missing ingredients to the grocery
    list, and report. Does not start cooking."""
    recipe = recipes.resolve(dish)
    if not recipe:
        return f"I don't have a recipe for {dish}."
    missing = _missing(recipe.get("ingredients", ""), db.get_inventory())
    if not missing:
        return f"You've got everything for {recipe['title']}!"
    add(missing)
    return "Adding missing ingredients: " + _join(missing) + "."


def answer_list():
    its = items()
    if not its:
        return "Your grocery list is empty."
    return "Your grocery list has " + _join(its) + "."


def _parse_item(text):
    """Pull the item out of "add X to my grocery list" / "remove X from my list"."""
    t = _norm(text)
    t = re.sub(r"^(add|put|remove|take off|take|delete|drop)\s+", "", t)
    t = re.sub(r"\s+(to|from|on|off)?\s*(my|the)?\s*(grocery|shopping)?\s*list.*$", "", t)
    t = re.sub(r"\s+(to|from)\s+(my|the)\b.*$", "", t)
    return t.strip()


def add_from_text(text):
    item = _parse_item(text)
    if item:
        add([item])
    return item


def remove_from_text(text):
    item = _parse_item(text)
    if item:
        remove([item])
    return item


def handle(text):
    """Dispatch a grocery-list voice command: clear / add / remove / read."""
    t = _norm(text)
    if any(k in t for k in ("clear", "empty", "reset", "delete everything",
                            "remove everything", "delete the whole", "start over")):
        clear()
        return "Okay, I've cleared your grocery list."
    if "add" in t or "put" in t:
        item = _parse_item(text)
        if item:
            return (f"Added {item} to your grocery list." if add([item])
                    else f"{item} is already on your list.")
    if "remove" in t or "take off" in t or "delete" in t or "drop" in t:
        item = _parse_item(text)
        if item:
            return (f"Removed {item} from your grocery list." if remove([item])
                    else f"I didn't find {item} on your list.")
    return answer_list()

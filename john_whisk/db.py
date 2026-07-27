import sqlite3
import contextlib
import datetime
from john_whisk import config


def _conn():
    return sqlite3.connect(config.DB_PATH)


def init_db():
    with contextlib.closing(_conn()) as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS inventory (
                   id       INTEGER PRIMARY KEY,
                   name     TEXT NOT NULL,
                   quantity REAL,
                   unit     TEXT,
                   added_at TEXT NOT NULL,
                   category TEXT)"""
        )
        # migrate a DB created before the category column existed
        cols = [r[1] for r in c.execute("PRAGMA table_info(inventory)").fetchall()]
        if "category" not in cols:
            c.execute("ALTER TABLE inventory ADD COLUMN category TEXT")
        c.commit()


def add_items(items):
    """Insert items, merging by name: sum numeric quantities; vague (None) -> None."""
    init_db()
    now = datetime.datetime.now().isoformat(timespec="seconds")
    with contextlib.closing(_conn()) as c:
        for it in items:
            name = it["name"]
            qty = it.get("quantity")
            unit = it.get("unit")
            category = it.get("category")
            row = c.execute(
                "SELECT id, quantity FROM inventory WHERE name = ?", (name,)
            ).fetchone()
            if row:
                existing = row[1]
                merged = None if (qty is None or existing is None) else existing + qty
                c.execute(
                    "UPDATE inventory SET quantity = ?, unit = COALESCE(?, unit), "
                    "category = COALESCE(?, category), added_at = ? WHERE id = ?",
                    (merged, unit, category, now, row[0]),
                )
            else:
                c.execute(
                    "INSERT INTO inventory (name, quantity, unit, added_at, category) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (name, qty, unit, now, category),
                )
        c.commit()


def _singular(s):
    """Naive singularizer so spoken "eggs" matches a stored "egg" (and vice
    versa). Good enough for pantry words; not a full inflection engine."""
    s = s.strip().lower()
    if len(s) > 3 and s.endswith("ies"):
        return s[:-3] + "y"
    if len(s) > 2 and s.endswith("es"):
        return s[:-2]
    if len(s) > 1 and s.endswith("s"):
        return s[:-1]
    return s


def remove_items(names):
    """Delete inventory rows matching any spoken name (case-insensitive, with
    simple singular/plural tolerance). Returns the stored names removed."""
    init_db()
    removed = []
    with contextlib.closing(_conn()) as c:
        rows = c.execute("SELECT id, name FROM inventory").fetchall()
        used = set()
        for spoken in names:
            target = _singular(spoken)
            for rid, name in rows:
                if rid not in used and _singular(name) == target:
                    c.execute("DELETE FROM inventory WHERE id = ?", (rid,))
                    removed.append(name)
                    used.add(rid)
                    break
        c.commit()
    return removed


def _plural_eq(a, b):
    """True if a and b are the same word ignoring a trailing-s plural, so a
    spoken "sauces" matches the category "sauce" and "eggs" matches "egg"."""
    a, b = a.strip().lower(), b.strip().lower()
    return a == b or a == b + "s" or b == a + "s" or _singular(a) == _singular(b)


def match_query(term):
    """Return the stored names of items whose NAME or CATEGORY matches `term`
    (plural-tolerant). Answers "do we have X" straight from the DB — no LLM —
    and makes category queries ("sauces", "pasta") list the tagged items."""
    init_db()
    with contextlib.closing(_conn()) as c:
        rows = c.execute("SELECT name, category FROM inventory").fetchall()
    out = []
    for name, category in rows:
        if _plural_eq(name, term) or (category and _plural_eq(category, term)):
            out.append(name)
    return out


def set_category(name, category):
    """Set an item's category (used by the one-time backfill of pre-tag items)."""
    init_db()
    with contextlib.closing(_conn()) as c:
        c.execute("UPDATE inventory SET category = ? WHERE name = ?", (category, name))
        c.commit()


def get_inventory():
    init_db()
    with contextlib.closing(_conn()) as c:
        rows = c.execute(
            "SELECT name, quantity, unit, category FROM inventory ORDER BY name"
        ).fetchall()
    return [{"name": r[0], "quantity": r[1], "unit": r[2], "category": r[3]} for r in rows]

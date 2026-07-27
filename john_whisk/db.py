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
                   added_at TEXT NOT NULL)"""
        )
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
            row = c.execute(
                "SELECT id, quantity FROM inventory WHERE name = ?", (name,)
            ).fetchone()
            if row:
                existing = row[1]
                merged = None if (qty is None or existing is None) else existing + qty
                c.execute(
                    "UPDATE inventory SET quantity = ?, unit = COALESCE(?, unit), added_at = ? WHERE id = ?",
                    (merged, unit, now, row[0]),
                )
            else:
                c.execute(
                    "INSERT INTO inventory (name, quantity, unit, added_at) VALUES (?, ?, ?, ?)",
                    (name, qty, unit, now),
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


def find_items(names):
    """For each queried name, return (queried, stored_name or None), matching
    with the same singular/plural tolerance as removal. Lets callers answer
    "do we have X" straight from the DB — no LLM, so no invented inventory."""
    init_db()
    with contextlib.closing(_conn()) as c:
        stored = [r[0] for r in c.execute("SELECT name FROM inventory").fetchall()]
    out = []
    for q in names:
        target = _singular(q)
        match = next((s for s in stored if _singular(s) == target), None)
        out.append((q, match))
    return out


def get_inventory():
    init_db()
    with contextlib.closing(_conn()) as c:
        rows = c.execute(
            "SELECT name, quantity, unit FROM inventory ORDER BY name"
        ).fetchall()
    return [{"name": r[0], "quantity": r[1], "unit": r[2]} for r in rows]

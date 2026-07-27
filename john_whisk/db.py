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


def get_inventory():
    init_db()
    with contextlib.closing(_conn()) as c:
        rows = c.execute(
            "SELECT name, quantity, unit FROM inventory ORDER BY name"
        ).fetchall()
    return [{"name": r[0], "quantity": r[1], "unit": r[2]} for r in rows]

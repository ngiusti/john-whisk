"""Runtime, user-editable settings (toggles, secrets, URLs, location) stored in
the DB so they can be changed from the dashboard without touching code."""
import contextlib
import sqlite3

from john_whisk import config


def _conn():
    return sqlite3.connect(config.DB_PATH)


def init_db():
    with contextlib.closing(_conn()) as c:
        c.execute("CREATE TABLE IF NOT EXISTS app_settings ("
                  "key TEXT PRIMARY KEY, value TEXT)")
        c.commit()


def get(key, default=None):
    init_db()
    with contextlib.closing(_conn()) as c:
        row = c.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def set(key, value):
    init_db()
    with contextlib.closing(_conn()) as c:
        c.execute("INSERT INTO app_settings (key, value) VALUES (?, ?) "
                  "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                  (key, str(value)))
        c.commit()


def get_bool(key, default=False):
    v = get(key)
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def all():
    init_db()
    with contextlib.closing(_conn()) as c:
        return dict(c.execute("SELECT key, value FROM app_settings").fetchall())

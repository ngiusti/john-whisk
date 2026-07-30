"""Pantry expiration alerts. `now` is injected so age math is deterministic;
inventory rows are inserted with crafted `added_at` dates."""
import contextlib
import datetime
import sqlite3

from john_whisk import config, expiration

NOW = datetime.datetime(2026, 1, 15, 12, 0, 0)


def _add(tmp_path, monkeypatch, rows):
    """rows: list of (name, category, days_ago)."""
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "p.db"))
    from john_whisk import db
    db.init_db()
    with contextlib.closing(sqlite3.connect(config.DB_PATH)) as c:
        for name, category, days_ago in rows:
            added = (NOW - datetime.timedelta(days=days_ago)).isoformat(timespec="seconds")
            c.execute("INSERT INTO inventory (name, quantity, unit, added_at, category) "
                      "VALUES (?, ?, ?, ?, ?)", (name, None, None, added, category))
        c.commit()


def test_shelf_life_defaults():
    assert expiration.shelf_life("vegetable") == 7
    assert expiration.shelf_life("spice") == 730
    assert expiration.shelf_life(None) == expiration.DEFAULT_SHELF_LIFE


def test_expiring_flags_old_perishables(tmp_path, monkeypatch):
    _add(tmp_path, monkeypatch, [("spinach", "vegetable", 10),
                                 ("rice", "grain", 10), ("chicken", "protein", 5)])
    names = {e["name"] for e in expiration.expiring(now=NOW)}
    assert "spinach" in names        # 10d old, 7d shelf -> expired
    assert "chicken" in names        # 5d old, 4d shelf -> expired
    assert "rice" not in names       # 10d old, 180d shelf -> fresh


def test_status_values(tmp_path, monkeypatch):
    _add(tmp_path, monkeypatch, [("spinach", "vegetable", 10),
                                 ("milk", "dairy", 13), ("flour", "baking", 1)])
    by = {s["name"]: s for s in expiration.annotate(now=NOW)}
    assert by["spinach"]["status"] == "expired"
    assert by["milk"]["status"] == "soon"       # 13d old, 14d shelf -> 1 left
    assert by["flour"]["status"] == "fresh"


def test_answer_expiring_empty(tmp_path, monkeypatch):
    _add(tmp_path, monkeypatch, [("rice", "grain", 5)])
    assert "nothing" in expiration.answer_expiring(now=NOW).lower()


def test_answer_expiring_lists_items(tmp_path, monkeypatch):
    _add(tmp_path, monkeypatch, [("spinach", "vegetable", 10)])
    assert "spinach" in expiration.answer_expiring(now=NOW).lower()


def test_router_expiring_intent():
    from john_whisk import router
    assert router.classify("what's going bad") == "expiring"
    assert router.classify("what should I use up") == "expiring"   # not 'suggest'
    assert router.classify("anything expiring soon") == "expiring"

"""Offline nutrition: a curated local food table (USDA-derived, public domain)
for calorie/macro lookups, with a flagged llama3.2 fallback for foods not in the
table. Numbers are approximations — awareness, not a medical tracker."""
import contextlib
import json
import re
import sqlite3

from john_whisk import config, llm

_MACROS = ("calories", "protein", "carbs", "fat")


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


def init_db():
    with contextlib.closing(_conn()) as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS nutrition_foods (
                   id       INTEGER PRIMARY KEY,
                   name     TEXT NOT NULL UNIQUE,
                   aliases  TEXT,
                   calories REAL, protein REAL, carbs REAL, fat REAL,
                   portions TEXT)"""
        )
        empty = c.execute("SELECT COUNT(*) FROM nutrition_foods").fetchone()[0] == 0
        c.commit()
    if empty:
        _load_seed()


def _load_seed():
    try:
        with open(config.NUTRITION_SEED_PATH, encoding="utf-8") as f:
            foods = json.load(f)
    except (OSError, ValueError):
        return
    with contextlib.closing(_conn()) as c:
        for food in foods:
            p = food.get("per_100g", {})
            c.execute(
                "INSERT OR IGNORE INTO nutrition_foods "
                "(name, aliases, calories, protein, carbs, fat, portions) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (food["name"].lower(),
                 json.dumps([a.lower() for a in food.get("aliases", [])]),
                 p.get("calories"), p.get("protein"), p.get("carbs"), p.get("fat"),
                 json.dumps(food.get("portions", {}))))
        c.commit()


def _row_to_food(row):
    name, aliases, cal, pro, carb, fat, portions = row
    return {"name": name, "aliases": json.loads(aliases or "[]"),
            "per_100g": {"calories": cal, "protein": pro, "carbs": carb, "fat": fat},
            "portions": json.loads(portions or "{}")}


def lookup(food):
    """Best matching food entry for an ingredient/food name, or None. Matches when
    an entry's name (or an alias), reduced to singular words, is a subset of the
    query words — so "cooked white rice" finds "white rice". Prefers the entry
    whose matched key has the most words (most specific)."""
    init_db()
    qw = _words(food)
    if not qw:
        return None
    best, best_len = None, 0
    with contextlib.closing(_conn()) as c:
        rows = c.execute(
            "SELECT name, aliases, calories, protein, carbs, fat, portions "
            "FROM nutrition_foods").fetchall()
    for row in rows:
        entry = _row_to_food(row)
        for key in [entry["name"], *entry["aliases"]]:
            kw = _words(key)
            if kw and kw <= qw and len(kw) > best_len:
                best, best_len = entry, len(kw)
    return best

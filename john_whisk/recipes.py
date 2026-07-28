"""Stored recipe library — a searchable repository John Whisk cooks from,
independent of the pantry DB. Cooking from a stored recipe needs no LLM."""
import sqlite3
import contextlib
import datetime
import json
import re

from john_whisk import config


def _conn():
    return sqlite3.connect(config.RECIPES_DB_PATH)


def _norm(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace — for match + dedupe."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", (text or "").lower())).strip()


def init_db():
    with contextlib.closing(_conn()) as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS recipes (
                   id          INTEGER PRIMARY KEY,
                   title       TEXT NOT NULL,
                   title_norm  TEXT NOT NULL,
                   ingredients TEXT,
                   steps       TEXT,
                   source      TEXT,
                   tags        TEXT,
                   added_at    TEXT NOT NULL)"""
        )
        c.commit()


def add_recipe(title, ingredients, steps, source="", tags="") -> bool:
    """Insert a recipe, deduped by normalized title. `ingredients` may be a list
    or a string; `steps` is a list. Returns True if added, False if a recipe with
    the same normalized title already exists."""
    init_db()
    title_norm = _norm(title)
    if isinstance(ingredients, (list, tuple)):
        ingredients = ", ".join(str(i) for i in ingredients)
    steps_json = json.dumps(list(steps))
    now = datetime.datetime.now().isoformat(timespec="seconds")
    with contextlib.closing(_conn()) as c:
        exists = c.execute("SELECT 1 FROM recipes WHERE title_norm = ?", (title_norm,)).fetchone()
        if exists:
            return False
        c.execute(
            "INSERT INTO recipes (title, title_norm, ingredients, steps, source, tags, added_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (title, title_norm, ingredients, steps_json, source, tags, now),
        )
        c.commit()
    return True


def _row_to_recipe(row):
    return {"title": row[0], "ingredients": row[1] or "", "steps": json.loads(row[2] or "[]")}


def _similarity(query_norm, title_norm) -> float:
    """Jaccard word overlap, with exact match forced to 1.0."""
    if query_norm == title_norm:
        return 1.0
    q, t = set(query_norm.split()), set(title_norm.split())
    if not q or not t:
        return 0.0
    return len(q & t) / len(q | t)


def _scored(query):
    init_db()
    qn = _norm(query)
    with contextlib.closing(_conn()) as c:
        rows = c.execute("SELECT id, title_norm FROM recipes").fetchall()
    return sorted(((_similarity(qn, tn), rid) for rid, tn in rows), reverse=True)


def find(dish):
    """Best stored recipe for a spoken dish, or None if nothing is close enough.
    Returns {title, ingredients (str), steps (list)}."""
    scored = _scored(dish)
    if not scored or scored[0][0] < config.RECIPE_MATCH_THRESHOLD:
        return None
    best_id = scored[0][1]
    with contextlib.closing(_conn()) as c:
        row = c.execute(
            "SELECT title, ingredients, steps FROM recipes WHERE id = ?", (best_id,)
        ).fetchone()
    return _row_to_recipe(row) if row else None


def search(query, limit=5):
    """Ranked stored recipes matching the query (for "what recipes do you have")."""
    scored = [(s, rid) for s, rid in _scored(query) if s >= config.RECIPE_MATCH_THRESHOLD][:limit]
    out = []
    with contextlib.closing(_conn()) as c:
        for _, rid in scored:
            row = c.execute(
                "SELECT title, ingredients, steps FROM recipes WHERE id = ?", (rid,)
            ).fetchone()
            if row:
                out.append(_row_to_recipe(row))
    return out


def count() -> int:
    init_db()
    with contextlib.closing(_conn()) as c:
        return c.execute("SELECT COUNT(*) FROM recipes").fetchone()[0]


def list_titles(limit=5):
    init_db()
    with contextlib.closing(_conn()) as c:
        rows = c.execute(
            "SELECT title FROM recipes ORDER BY added_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [r[0] for r in rows]


def _join(parts) -> str:
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return parts[0] + " and " + parts[1]
    return ", ".join(parts[:-1]) + ", and " + parts[-1]


# Lead-ins before a specific dish in a "do you have a recipe for X" question.
_QUERY_LEADINS = [
    "do you have a recipe for", "do we have a recipe for", "got a recipe for",
    "is there a recipe for", "do you know a recipe for",
    "what recipes do you have for", "the recipe for", "a recipe for", "recipe for",
]


def answer_query(text: str) -> str:
    """Answer a question about the stored recipe library, straight from the DB
    (no LLM). Handles "how many recipes", "what recipes do you have", and
    "do you have a recipe for X"."""
    t = _norm(text)
    if "how many" in t:
        n = count()
        return f"I have {n} recipe{'s' if n != 1 else ''} saved."
    best_end = -1
    for lead in _QUERY_LEADINS:
        idx = t.find(lead)
        if idx != -1 and idx + len(lead) > best_end:
            best_end = idx + len(lead)
    dish = t[best_end:].strip() if best_end != -1 else ""
    if not dish:                                   # general "what recipes do you have"
        n = count()
        if n == 0:
            return "I don't have any recipes saved yet."
        return f"I have {n} recipes saved, like " + _join(list_titles(3)) + "."
    hits = search(dish, limit=3)
    if hits:
        return "Yes, I've got " + _join([h["title"] for h in hits]) + "."
    return (f"No, I don't have a recipe for {dish} saved, "
            "but I can make one up if you'd like.")

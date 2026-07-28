"""Recipe ratings & history: thumbs up/down on cooked meals, so suggestions
favor what you like and drop what you dislike. Deterministic parsing; ratings
bias the suggest prompt (not hard blocks)."""
import sqlite3
import contextlib
import datetime
import re

from john_whisk import config

# sentiment keywords (normalized). Negatives are checked first — some contain
# "like" ("didn't like").
_NEG = ["didn t like", "don t like", "do not like", "didn t enjoy", "don t suggest",
        "dont suggest", "never again", "never make", "hate", "hated", "terrible",
        "awful", "dislike", "gross", "disgusting", "nasty", "not good", "worst", "bad"]
_POS = ["great", "loved", "love", "liked", "like", "delicious", "amazing", "good",
        "favorite", "favourite", "excellent", "tasty", "enjoyed", "enjoy", "yum", "best"]

_RATE_LEADINS = [
    "i really love", "i love", "i loved", "i really like", "i like", "i liked",
    "i enjoyed", "i really enjoyed", "i don t like", "i didn t like", "i dont like",
    "i do not like", "i hate", "i hated", "rate the", "rate", "that was",
    "this was", "don t suggest", "dont suggest", "never make", "never again",
    "i think", "we loved", "we liked",
]
_FILLER = {"the", "a", "an", "that", "this", "it", "again", "one", "dish", "meal",
           "recipe", "my", "really", "so", "very", "was", "is", "them", "those"}
_SENT_WORDS = set(w for p in (_POS + _NEG) for w in p.split())


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


# --- store ----------------------------------------------------------------

def init_db():
    with contextlib.closing(_conn()) as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS ratings (
                   id           INTEGER PRIMARY KEY,
                   recipe       TEXT NOT NULL,
                   title_norm   TEXT NOT NULL UNIQUE,
                   rating       INTEGER NOT NULL DEFAULT 0,
                   cooked_count INTEGER NOT NULL DEFAULT 0,
                   last_at      TEXT)"""
        )
        c.commit()


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def cooked(title):
    """Record that a recipe was cooked (defines the 'last cooked' target)."""
    init_db()
    n = _norm(title)
    if not n:
        return
    with contextlib.closing(_conn()) as c:
        row = c.execute("SELECT id FROM ratings WHERE title_norm = ?", (n,)).fetchone()
        if row:
            c.execute("UPDATE ratings SET cooked_count = cooked_count + 1, last_at = ? "
                      "WHERE id = ?", (_now(), row[0]))
        else:
            c.execute("INSERT INTO ratings (recipe, title_norm, rating, cooked_count, last_at) "
                      "VALUES (?, ?, 0, 1, ?)", (title, n, _now()))
        c.commit()


def last_cooked():
    init_db()
    with contextlib.closing(_conn()) as c:
        row = c.execute("SELECT recipe FROM ratings WHERE cooked_count > 0 "
                        "ORDER BY last_at DESC, id DESC LIMIT 1").fetchone()
    return row[0] if row else None


def rate(title, up):
    init_db()
    n = _norm(title)
    if not n:
        return
    val = 1 if up else -1
    with contextlib.closing(_conn()) as c:
        row = c.execute("SELECT id FROM ratings WHERE title_norm = ?", (n,)).fetchone()
        if row:
            c.execute("UPDATE ratings SET rating = ? WHERE id = ?", (val, row[0]))
        else:
            c.execute("INSERT INTO ratings (recipe, title_norm, rating, cooked_count, last_at) "
                      "VALUES (?, ?, ?, 0, ?)", (title, n, val, _now()))
        c.commit()


def _titles_with(rating):
    init_db()
    with contextlib.closing(_conn()) as c:
        return [r[0] for r in c.execute(
            "SELECT recipe FROM ratings WHERE rating = ? ORDER BY last_at, id", (rating,)).fetchall()]


def favorites():
    return _titles_with(1)


def disliked():
    return _titles_with(-1)


def clear():
    init_db()
    with contextlib.closing(_conn()) as c:
        c.execute("DELETE FROM ratings")
        c.commit()


# --- parsing + messaging --------------------------------------------------

def _sentiment(t):
    if any(k in t for k in _NEG):
        return -1
    if any(k in t for k in _POS):
        return 1
    return 0


def _target(text):
    t = _norm(text)
    best_end = -1
    for lead in _RATE_LEADINS:
        idx = t.find(lead)
        if idx != -1 and idx + len(lead) > best_end:
            best_end = idx + len(lead)
    tail = t[best_end:].strip() if best_end != -1 else t
    words = [w for w in tail.split() if w not in _FILLER and w not in _SENT_WORDS]
    return " ".join(words).strip() or None


def rate_from_text(text):
    """Apply a spoken rating. Returns (target_title, sentiment) or None."""
    s = _sentiment(_norm(text))
    if s == 0:
        return None
    target = _target(text) or last_cooked()
    if not target:
        return None
    rate(target, s == 1)
    return (target, s)


def preference_clause():
    """A clause for the suggest prompt reflecting likes/dislikes ("" if none)."""
    d, l = disliked(), favorites()
    if not d and not l:
        return ""
    parts = []
    if d:
        parts.append("Do not suggest " + _join(d) + ".")
    if l:
        parts.append("I especially enjoy " + _join(l) + ".")
    return " ".join(parts) + " "


def answer_favorites():
    f = favorites()
    if not f:
        return "You haven't rated any recipes as favorites yet."
    return "Your favorites are " + _join(f) + "."


def handle(text):
    t = _norm(text)
    if "favorite" in t or "favourite" in t or ("what" in t and ("like" in t or "love" in t)):
        return answer_favorites()
    res = rate_from_text(text)
    if not res:
        return "I'm not sure which recipe you mean."
    target, s = res
    return (f"Glad you liked {target} — I'll suggest it more." if s == 1
            else f"Got it — I won't suggest {target} anymore.")

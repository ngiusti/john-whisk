"""Flavor customization: live mid-recipe adjustment tips ("tone down the spice")
plus a saved flavor preference that nudges suggestions. Advice is LLM-generated
(grounded in the recipe/step); the preference is a soft bias."""
import sqlite3
import contextlib
import datetime
import re

from john_whisk import config, llm

# in-recipe flavor-adjustment cues (NOT "how hot should the pan be" — that's a
# question, handled by the normal fallthrough).
_ADJUST = [
    "tone down", "tone it down", "dial back", "dial it back", "spice it up",
    "kick it up", "punch it up", "spicier", "hotter", "milder", "make it mild",
    "make it bold", "bolder", "too spicy", "too hot", "too salty", "too bland",
    "too sweet", "too sour", "too much", "not enough", "more flavor", "more spice",
    "more garlic", "more salt", "less salt", "less spicy", "less heat", "more heat",
    "make it sweeter", "make it tangier", "make it richer", "needs more", "need more",
    "add more", "season it", "more seasoning", "less sweet",
]
_NEG = ["don t", "dont", "do not", "not ", "less ", "isn t", "too "]
_PREF_LEADINS = [
    "we really like it", "we like it", "we like our food", "we like our meals",
    "we prefer our food", "we prefer", "we enjoy", "i like it", "keep it",
    "keep things", "make everything", "we don t like it too", "we dont like it too",
    "we don t like it", "we do not like it", "we like things", "we like",
]
_PREF_FILLER = {"the", "a", "an", "it", "food", "meals", "flavor", "flavors",
                "flavour", "flavours", "taste", "very", "really", "our", "them",
                "things", "everything", "kind", "of", "bit"}


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


# --- preference store -----------------------------------------------------

def init_db():
    with contextlib.closing(_conn()) as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS flavor_prefs (
                   id       INTEGER PRIMARY KEY,
                   note     TEXT NOT NULL UNIQUE,
                   added_at TEXT NOT NULL)"""
        )
        c.commit()


def add(notes):
    if isinstance(notes, str):
        notes = [notes]
    init_db()
    now = datetime.datetime.now().isoformat(timespec="seconds")
    with contextlib.closing(_conn()) as c:
        for n in notes:
            n = str(n).strip().lower()
            if n:
                c.execute("INSERT OR IGNORE INTO flavor_prefs (note, added_at) VALUES (?, ?)",
                          (n, now))
        c.commit()


def remove(notes):
    if isinstance(notes, str):
        notes = [notes]
    init_db()
    with contextlib.closing(_conn()) as c:
        for n in notes:
            c.execute("DELETE FROM flavor_prefs WHERE note = ?", (str(n).strip().lower(),))
        c.commit()


def prefs():
    init_db()
    with contextlib.closing(_conn()) as c:
        return [r[0] for r in c.execute(
            "SELECT note FROM flavor_prefs ORDER BY added_at, id").fetchall()]


def clear():
    init_db()
    with contextlib.closing(_conn()) as c:
        c.execute("DELETE FROM flavor_prefs")
        c.commit()


# --- live in-recipe tips --------------------------------------------------

def is_adjust(text):
    return any(k in _norm(text) for k in _ADJUST)


def tip(title, step, request):
    """Practical flavor advice for the current step, grounded in saved prefs."""
    return (llm.flavor_advice(title, step, request, ", ".join(prefs()))
            or "Sorry, I couldn't think of a flavor tip right now.")


# --- preferences: parse / read / clause -----------------------------------

def prompt_clause():
    p = prefs()
    if not p:
        return ""
    return "We like our food " + _join(p) + ". "


def set_from_text(text):
    t = _norm(text)
    negated = any(n in (" " + t + " ") for n in _NEG)
    best_end = -1
    for lead in _PREF_LEADINS:
        idx = t.find(lead)
        if idx != -1 and idx + len(lead) > best_end:
            best_end = idx + len(lead)
    tail = t[best_end:].strip() if best_end != -1 else t
    words = [w for w in tail.split() if w not in _PREF_FILLER]
    desc = " ".join(words).strip()
    if not desc:
        return None
    note = ("not too " + desc) if negated else desc
    add([note])
    return note


def answer_prefs():
    p = prefs()
    if not p:
        return "You haven't set any flavor preferences yet."
    return "You like your food " + _join(p) + "."


def handle(text):
    t = _norm(text)
    if "clear" in t or "reset" in t or "no preference" in t:
        clear()
        return "Okay, I've cleared your flavor preferences."
    if "what" in t or "list" in t or "my flavor" in t or "our flavor" in t:
        return answer_prefs()
    note = set_from_text(text)
    if note:
        return f"Got it — I'll keep your {note} preference in mind."
    return "I'm not sure what flavor you mean."

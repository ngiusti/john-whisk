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


_FRACTIONS = {"½": 0.5, "¼": 0.25, "¾": 0.75, "⅓": 1 / 3,
              "⅔": 2 / 3, "⅛": 0.125, "⅜": 0.375, "⅝": 0.625,
              "⅞": 0.875}
_NUMWORDS = {"a": 1.0, "an": 1.0, "one": 1.0, "two": 2.0, "three": 3.0, "four": 4.0,
             "five": 5.0, "six": 6.0, "seven": 7.0, "eight": 8.0, "nine": 9.0,
             "ten": 10.0, "dozen": 12.0, "half": 0.5}
# canonical unit -> the token spellings that map to it
_UNIT_ALIASES = {
    "cup": ["cup", "cups"], "tablespoon": ["tablespoon", "tablespoons", "tbsp"],
    "teaspoon": ["teaspoon", "teaspoons", "tsp"], "ounce": ["ounce", "ounces", "oz"],
    "pound": ["pound", "pounds", "lb", "lbs"], "gram": ["gram", "grams", "g"],
    "kilogram": ["kilogram", "kilograms", "kg"], "ml": ["ml", "milliliter", "milliliters"],
    "liter": ["liter", "liters", "litre", "litres", "l"], "pint": ["pint", "pints"],
    "quart": ["quart", "quarts"], "clove": ["clove", "cloves"], "slice": ["slice", "slices"],
    "can": ["can", "cans"], "stick": ["stick", "sticks"], "large": ["large"],
    "medium": ["medium"], "small": ["small"], "pinch": ["pinch", "pinches"],
    "breast": ["breast", "breasts"],
}
_UNIT_OF = {tok: canon for canon, toks in _UNIT_ALIASES.items() for tok in toks}


def _leading_number(tokens):
    """Consume a leading quantity (digits, fractions, unicode fractions, mixed
    numbers, or a number word). Returns (qty_or_None, remaining_tokens)."""
    if not tokens:
        return None, tokens
    t0 = tokens[0]
    # unicode fraction possibly glued to a number, e.g. "1½"
    for gl, val in _FRACTIONS.items():
        if t0.endswith(gl):
            whole = t0[:-len(gl)]
            base = float(whole) if whole.replace(".", "", 1).isdigit() else 0.0
            return base + val, tokens[1:]
    if re.fullmatch(r"\d+/\d+", t0):
        n, d = t0.split("/")
        if int(d) != 0:
            return int(n) / int(d), tokens[1:]
        return None, tokens                          # malformed "n/0": not a quantity
    if re.fullmatch(r"\d+(\.\d+)?", t0):
        val = float(t0)
        if len(tokens) > 1 and re.fullmatch(r"\d+/\d+", tokens[1]):   # mixed "1 1/2"
            n, d = tokens[1].split("/")
            if int(d) != 0:
                return val + int(n) / int(d), tokens[2:]
        return val, tokens[1:]
    if t0 in _NUMWORDS:
        return _NUMWORDS[t0], tokens[1:]
    return None, tokens


def parse_ingredient(line):
    """Parse "1 cup uncooked rice" -> (1.0, "cup", "uncooked rice"). Returns
    (quantity|None, unit|None, food). When no quantity is present the whole line
    is the food (unit None)."""
    raw = re.sub(r"\s+", " ", (line or "").strip().lower())
    if not raw:
        return None, None, ""
    tokens = raw.split()
    qty, rest = _leading_number(tokens)
    if qty is None:
        return None, None, raw                       # no leading number: all food
    unit = None
    if rest and rest[0] in _UNIT_OF:
        unit = _UNIT_OF[rest[0]]
        rest = rest[1:]
        if rest and rest[0] == "of":                 # "a pinch of salt"
            rest = rest[1:]
    return qty, unit, " ".join(rest)


_MASS_G = {"gram": 1.0, "kilogram": 1000.0, "ounce": 28.35, "pound": 453.6}
_VOL_APPROX_G = {"cup": 240.0, "tablespoon": 15.0, "teaspoon": 5.0, "ml": 1.0,
                 "liter": 1000.0, "pint": 473.0, "quart": 946.0}


def to_grams(quantity, unit, food):
    """Best-effort conversion of quantity+unit of a food to grams, or None if it
    can't be determined. Order: the food's own household portion, then direct
    mass units, then a generic volume approximation. A bare count ("2 eggs")
    uses the food's "each" portion."""
    if quantity is None:
        return None
    portions = {}
    entry = lookup(food)
    if entry:
        portions = {k.lower(): v for k, v in entry["portions"].items()}
    if unit is None:
        return quantity * portions["each"] if "each" in portions else None
    if unit in portions:
        return quantity * portions[unit]
    if unit in _MASS_G:
        return quantity * _MASS_G[unit]
    if unit in _VOL_APPROX_G:
        return quantity * _VOL_APPROX_G[unit]
    return None


def _zero():
    return {m: 0.0 for m in _MACROS}


def for_food(quantity, unit, food):
    """Nutrition for one food amount as {calories, protein, carbs, fat,
    estimated}. Uses the local table + gram conversion when possible; otherwise
    an LLM estimate (estimated=True). Returns None if neither yields data."""
    entry = lookup(food)
    grams = to_grams(quantity, unit, food) if entry else None
    if entry and grams is not None:
        factor = grams / 100.0
        out = {m: round((entry["per_100g"].get(m) or 0.0) * factor, 1) for m in _MACROS}
        out["estimated"] = False
        return out
    phrase = " ".join(str(x) for x in (quantity, unit, food) if x)
    est = llm.estimate_nutrition(phrase)
    if est is None:
        return None
    out = {m: round(float(est.get(m, 0.0)), 1) for m in _MACROS}
    out["estimated"] = True
    return out

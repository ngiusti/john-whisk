"""Seasonal & budget recipe modes. Seasonal uses a curated month->produce map
(Northern Hemisphere); budget uses a curated expensive-ingredient set as a
cheapness heuristic (no price data). Both scan the stored library, offline."""
import contextlib
import re
import sqlite3

from john_whisk import config, recipes

# Roughly what's in season by month (Northern Hemisphere). A guide, not gospel.
SEASONAL = {
    1: ["kale", "cabbage", "leek", "potato", "carrot", "onion", "orange", "grapefruit", "beet", "squash"],
    2: ["kale", "cabbage", "leek", "orange", "potato", "carrot", "beet", "turnip", "squash", "citrus"],
    3: ["spinach", "leek", "kale", "cabbage", "carrot", "radish", "artichoke", "scallion"],
    4: ["asparagus", "pea", "spinach", "radish", "artichoke", "rhubarb", "lettuce", "scallion"],
    5: ["asparagus", "pea", "strawberry", "spinach", "radish", "lettuce", "rhubarb", "scallion"],
    6: ["strawberry", "cherry", "zucchini", "pea", "green bean", "lettuce", "cucumber", "apricot"],
    7: ["tomato", "zucchini", "corn", "cucumber", "blueberry", "peach", "pepper", "green bean", "melon"],
    8: ["tomato", "corn", "zucchini", "pepper", "eggplant", "peach", "plum", "melon", "cucumber"],
    9: ["apple", "grape", "pear", "squash", "pumpkin", "tomato", "pepper", "eggplant", "fig"],
    10: ["apple", "pumpkin", "squash", "sweet potato", "pear", "grape", "cranberry", "mushroom"],
    11: ["squash", "pumpkin", "sweet potato", "brussels sprout", "cranberry", "pear", "leek", "kale"],
    12: ["citrus", "orange", "pomegranate", "squash", "potato", "leek", "kale", "brussels sprout"],
}

# Ingredients that make a recipe pricey — a recipe with any of these is not
# "budget". Distinctive terms, matched as substrings of the ingredient text.
EXPENSIVE = ["steak", "ribeye", "filet", "tenderloin", "sirloin", "lamb", "veal",
             "duck", "shrimp", "prawn", "lobster", "crab", "scallop", "salmon",
             "tuna", "saffron", "truffle", "pine nut", "vanilla bean", "caviar",
             "cashew", "macadamia", "pecan", "prosciutto", "brie"]


def _now():
    import datetime
    return datetime.datetime.now()


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


def _join(parts):
    parts = list(parts)
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return parts[0] + " and " + parts[1]
    return ", ".join(parts[:-1]) + ", and " + parts[-1]


def in_season(month):
    return SEASONAL.get(month, [])


def _recipe_rows():
    recipes.init_db()
    with contextlib.closing(sqlite3.connect(config.RECIPES_DB_PATH)) as c:
        return c.execute("SELECT title, ingredients FROM recipes").fetchall()


def seasonal_recipes(month, limit=8):
    """Stored recipes featuring in-season produce, most in-season first."""
    produce = {_singular(p) for item in in_season(month) for p in [item]}
    scored = []
    for title, ingredients in _recipe_rows():
        iw = _words(ingredients)
        hits = len(produce & iw)
        if hits:
            scored.append((hits, len((ingredients or "").split(",")), title))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [{"title": t, "in_season": h} for h, _, t in scored[:limit]]


def budget_recipes(limit=8):
    """Stored recipes with NO expensive ingredients, simplest (fewest
    ingredients) first — a cheap-and-easy heuristic."""
    scored = []
    for title, ingredients in _recipe_rows():
        low = (ingredients or "").lower()
        if any(kw in low for kw in EXPENSIVE):
            continue
        n = len([x for x in (ingredients or "").split(",") if x.strip()])
        if n:
            scored.append((n, title))
    scored.sort()
    return [{"title": t, "ingredients_count": n} for n, t in scored[:limit]]


def answer_in_season(now=None):
    items = in_season((now or _now()).month)
    if not items:
        return "I'm not sure what's in season right now."
    return "In season right now: " + _join(items[:8]) + "."


def answer_seasonal(now=None):
    now = now or _now()
    msg = answer_in_season(now)
    recs = seasonal_recipes(now.month, limit=3)
    if recs:
        msg += " You could make " + _join([r["title"] for r in recs]) + "."
    return msg


def answer_budget():
    recs = budget_recipes(limit=4)
    if not recs:
        return "I couldn't find a budget-friendly recipe."
    return "Budget-friendly picks: " + _join([r["title"] for r in recs]) + "."

"""Offline nutrition: a curated local food table (USDA-derived, public domain)
for calorie/macro lookups, with a flagged llama3.2 fallback for foods not in the
table. Numbers are approximations — awareness, not a medical tracker."""
import contextlib
import datetime
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
        c.execute(
            """CREATE TABLE IF NOT EXISTS daily_log (
                   id       INTEGER PRIMARY KEY,
                   log_date TEXT NOT NULL,
                   food     TEXT,
                   calories REAL, protein REAL, carbs REAL, fat REAL,
                   logged_at TEXT NOT NULL)"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS nutrition_goals (
                   id       INTEGER PRIMARY KEY CHECK (id = 1),
                   calories REAL, protein REAL, carbs REAL, fat REAL)"""
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
    if entry and grams is None and quantity is None:
        grams = 100.0                      # bare food name -> per-100g from the table
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


def for_recipe(recipe, servings=None):
    """Sum a recipe's ingredient nutrition from the LOCAL table. Returns
    {total, per_serving, unmatched, estimated}. Ingredients the table can't
    resolve are listed in `unmatched` (not sent to the LLM here); `estimated`
    is True when anything was unmatched. `servings` defaults to
    config.DEFAULT_SERVINGS."""
    servings = servings or config.DEFAULT_SERVINGS
    total, unmatched = _zero(), []
    for ing in (recipe.get("ingredients") or "").split(","):
        ing = ing.strip()
        if not ing:
            continue
        qty, unit, food = parse_ingredient(ing)
        entry = lookup(food)
        grams = to_grams(qty, unit, food) if entry else None
        if entry and grams is not None:
            factor = grams / 100.0
            for m in _MACROS:
                total[m] += (entry["per_100g"].get(m) or 0.0) * factor
        else:
            unmatched.append(ing)
    total = {m: round(total[m], 1) for m in _MACROS}
    per_serving = {m: round(total[m] / servings, 1) for m in _MACROS}
    return {"total": total, "per_serving": per_serving,
            "unmatched": unmatched, "estimated": bool(unmatched)}


def describe(nutr, per_serving=True, estimated=False):
    """A short spoken nutrition sentence from a macro dict."""
    where = "a serving" if per_serving else "that"
    lead = "Roughly " if estimated else "About "
    return (f"{lead}{round(nutr['calories'])} calories {where}: "
            f"{round(nutr['protein'])} g protein, {round(nutr['carbs'])} g carbs, "
            f"{round(nutr['fat'])} g fat.")


_QUERY_LEADINS = [
    "how many calories are in", "how many calories in", "how much protein in",
    "how much fat in", "how many carbs in", "how many carbs are in",
    "calories in", "macros in", "macros for", "nutrition in", "nutrition for",
    "nutrition facts for", "calories for", "how many calories does", " in ",
]


def _subject(text):
    t = _norm(text)
    end = -1
    for lead in sorted(_QUERY_LEADINS, key=len, reverse=True):
        idx = t.find(lead)
        if idx != -1:
            end = max(end, idx + len(lead))
    subj = t[end:].strip() if end != -1 else t
    return re.sub(r"\b(have|do|does|are|is|there|the|a|an)\b", " ", subj).strip() \
        if end == -1 else subj


def answer_query(text):
    """Answer "calories/macros in X" for a stored recipe (per serving, cached) or
    an ad-hoc food. Returns a spoken sentence."""
    from john_whisk import recipes
    if any(p in _norm(text) for p in _STATUS_PHRASES):
        return answer_status()
    subject = _subject(text)
    if not subject:
        return "Which food or recipe do you want the nutrition for?"
    recipe = recipes.find(subject)
    if recipe:
        cached = recipes.get_nutrition(recipe["title"])
        if cached:
            return f"{recipe['title']}: " + describe(cached, per_serving=True)
        result = for_recipe(recipe)
        if any(result["per_serving"].values()):        # don't cache an all-zero result
            recipes.set_nutrition(recipe["title"], result["per_serving"])
        msg = f"{recipe['title']}: " + describe(
            result["per_serving"], per_serving=True, estimated=result["estimated"])
        if result["unmatched"]:
            msg += f" I couldn't score {len(result['unmatched'])} ingredient" \
                   f"{'s' if len(result['unmatched']) != 1 else ''}."
        return msg
    qty, unit, food = parse_ingredient(subject)
    out = for_food(qty, unit, food)
    if out is None:
        return f"I couldn't find nutrition for {subject}."
    return describe(out, per_serving=False, estimated=out["estimated"])


# --- Phase B: daily intake log + goals ------------------------------------

_STATUS_PHRASES = ("how am i doing", "what have i eaten", "what did i eat",
                   "how much have i eaten", "my intake", "so far today",
                   "calories today", "eaten today", "my total today")

# spoken goal field -> canonical macro
_GOAL_FIELD = {"calorie": "calories", "calories": "calories", "protein": "protein",
               "carb": "carbs", "carbs": "carbs", "carbohydrate": "carbs", "fat": "fat"}


def _today():
    return datetime.date.today().isoformat()


def _join(parts):
    parts = list(parts)
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return parts[0] + " and " + parts[1]
    return ", ".join(parts[:-1]) + ", and " + parts[-1]


def _insert_log(food, nutr):
    init_db()
    now = datetime.datetime.now().isoformat(timespec="seconds")
    with contextlib.closing(_conn()) as c:
        c.execute(
            "INSERT INTO daily_log (log_date, food, calories, protein, carbs, fat, logged_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (_today(), food, nutr["calories"], nutr["protein"], nutr["carbs"],
             nutr["fat"], now))
        c.commit()


def log_food(text):
    """Log what the user ate today. Handles "I ate a serving of <recipe>" (logs
    the recipe's per-serving nutrition) and free-form lists ("two eggs and
    toast"). Returns a spoken confirmation."""
    from john_whisk import recipes
    raw = _norm(text)
    m = re.search(r"serving of (.+)$", raw)
    if m:
        recipe = recipes.find(m.group(1).strip())
        if recipe:
            nutr = recipes.get_nutrition(recipe["title"]) or for_recipe(recipe)["per_serving"]
            _insert_log(f"{recipe['title']} (serving)", nutr)
            return f"Logged a serving of {recipe['title']}: about {round(nutr['calories'])} calories."
    body = re.sub(r"^(i just ate|i ate|i had|log|add|ate)\b", "", raw).strip()
    if not body:
        return "What did you eat?"
    logged, total = [], 0.0
    for frag in re.split(r"\s+and\s+|,", body):
        frag = frag.strip()
        if not frag:
            continue
        qty, unit, food = parse_ingredient(frag)
        nutr = for_food(qty, unit, food)
        if nutr:
            _insert_log(frag, nutr)
            logged.append(frag)
            total += nutr["calories"]
    if not logged:
        return "I couldn't work out the nutrition for that."
    return f"Logged {_join(logged)}. That's about {round(total)} calories."


def today():
    """Today's summed macros as {calories, protein, carbs, fat}."""
    init_db()
    with contextlib.closing(_conn()) as c:
        row = c.execute(
            "SELECT COALESCE(SUM(calories),0), COALESCE(SUM(protein),0), "
            "COALESCE(SUM(carbs),0), COALESCE(SUM(fat),0) "
            "FROM daily_log WHERE log_date = ?", (_today(),)).fetchone()
    return {m: round(row[i], 1) for i, m in enumerate(_MACROS)}


def today_entries():
    """Today's individual log rows (for the dashboard): [{id, food, calories, ...}]."""
    init_db()
    with contextlib.closing(_conn()) as c:
        rows = c.execute(
            "SELECT id, food, calories, protein, carbs, fat FROM daily_log "
            "WHERE log_date = ? ORDER BY id", (_today(),)).fetchall()
    return [{"id": r[0], "food": r[1], "calories": r[2], "protein": r[3],
             "carbs": r[4], "fat": r[5]} for r in rows]


def remove_log(entry_id):
    init_db()
    with contextlib.closing(_conn()) as c:
        c.execute("DELETE FROM daily_log WHERE id = ?", (entry_id,))
        c.commit()


def clear_today():
    init_db()
    with contextlib.closing(_conn()) as c:
        c.execute("DELETE FROM daily_log WHERE log_date = ?", (_today(),))
        c.commit()


def goals():
    """The daily goals as {calories, protein, carbs, fat}; a field is None if unset."""
    init_db()
    with contextlib.closing(_conn()) as c:
        row = c.execute(
            "SELECT calories, protein, carbs, fat FROM nutrition_goals WHERE id = 1").fetchone()
    if not row:
        return {m: None for m in _MACROS}
    return {m: row[i] for i, m in enumerate(_MACROS)}


def set_goal(field, value):
    """Set one daily goal (field in calories/protein/carbs/fat). Returns True if set."""
    field = field.lower()
    if field not in _MACROS:
        return False
    init_db()
    with contextlib.closing(_conn()) as c:
        c.execute("INSERT OR IGNORE INTO nutrition_goals (id, calories, protein, carbs, fat) "
                  "VALUES (1, NULL, NULL, NULL, NULL)")
        c.execute(f"UPDATE nutrition_goals SET {field} = ? WHERE id = 1", (float(value),))
        c.commit()
    return True


def remaining():
    """Goal minus today's total per macro; None where no goal is set."""
    g, t = goals(), today()
    return {m: (round(g[m] - t[m], 1) if g[m] is not None else None) for m in _MACROS}


def set_goal_from_text(text):
    """Set a goal from speech: "set my calorie goal to 2000" / "protein goal 150 grams"."""
    t = _norm(text)
    num = re.search(r"(\d+(?:\.\d+)?)", t)
    field = next((v for k, v in _GOAL_FIELD.items() if k in t), None)
    if not field:
        return "Which goal — calories, protein, carbs, or fat?"
    if not num:
        return f"What number should I set your {field} goal to?"
    set_goal(field, float(num.group(1)))
    return f"Set your daily {field} goal to {round(float(num.group(1)))}."


def answer_goals():
    g = goals()
    labels = {"calories": "calories", "protein": "grams protein",
              "carbs": "grams carbs", "fat": "grams fat"}
    have = [f"{round(v)} {labels[m]}" for m, v in g.items() if v is not None]
    if not have:
        return "You haven't set any nutrition goals yet."
    return "Your daily goals are " + _join(have) + "."


def goal_command(text):
    """Dispatch a goal utterance: a number means set, otherwise report goals."""
    if re.search(r"\d", text):
        return set_goal_from_text(text)
    return answer_goals()


def answer_status():
    """Spoken 'how am I doing today' — today's totals vs goals where set."""
    t, g = today(), goals()
    if not any(t[m] for m in _MACROS):
        return "You haven't logged any food today."
    labels = {"calories": "calories", "protein": "grams protein",
              "carbs": "grams carbs", "fat": "grams fat"}

    def seg(m):
        if g[m] is not None:
            return f"{round(t[m])} of {round(g[m])} {labels[m]}"
        return f"{round(t[m])} {labels[m]}"

    return "Today you've had " + _join([seg(m) for m in _MACROS]) + "."

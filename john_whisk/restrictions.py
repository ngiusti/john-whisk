"""Allergen & dietary restriction management. Keyword-rule detection (offline,
deterministic — the weak LLM is not trusted with allergen safety), with
restriction-compliant ingredient substitutions. Always caution to check labels:
a helpful filter, not a medical guarantee."""
import sqlite3
import contextlib
import datetime
import re

from john_whisk import config

_MEAT = ["chicken", "beef", "pork", "lamb", "turkey", "bacon", "ham", "sausage",
         "prosciutto", "meat", "veal", "duck", "salami", "pepperoni",
         "fish", "salmon", "tuna", "cod", "anchovy", "tilapia", "halibut",
         "sardine", "shrimp", "prawn", "crab", "lobster", "oyster", "clam",
         "mussel", "scallop", "shellfish", "seafood"]
_DAIRY = ["milk", "cheese", "butter", "cream", "yogurt", "parmesan",
          "mozzarella", "cheddar", "dairy"]

RULES = {
    "nuts": ["almond", "walnut", "pecan", "cashew", "peanut", "pistachio",
             "hazelnut", "pine nut", "macadamia", "nut"],
    "gluten": ["wheat", "flour", "bread", "pasta", "barley", "rye", "couscous",
               "breadcrumb", "cracker", "noodle", "gluten"],
    "dairy": _DAIRY,
    "eggs": ["egg"],
    "shellfish": ["shrimp", "prawn", "crab", "lobster", "oyster", "clam",
                  "mussel", "scallop", "shellfish"],
    "fish": ["fish", "salmon", "tuna", "cod", "anchovy", "tilapia", "halibut",
             "sardine"],
    "soy": ["soy", "tofu", "edamame", "miso"],
    "pork": ["pork", "bacon", "ham", "sausage", "prosciutto"],
    "vegetarian": list(_MEAT),
    "vegan": list(_MEAT) + _DAIRY + ["egg", "honey"],
}

SUBS = {
    "dairy": {"cream": "soy cream", "milk": "oat milk", "butter": "olive oil",
              "cheese": "dairy-free cheese", "parmesan": "nutritional yeast",
              "mozzarella": "dairy-free mozzarella", "cheddar": "dairy-free cheese",
              "yogurt": "coconut yogurt"},
    "gluten": {"flour": "gluten-free flour", "pasta": "gluten-free pasta",
               "bread": "gluten-free bread", "breadcrumb": "gluten-free breadcrumbs",
               "noodle": "rice noodles", "cracker": "gluten-free crackers"},
    "vegetarian": {"chicken": "tofu", "beef": "lentils", "pork": "mushrooms",
                   "bacon": "tempeh", "fish": "tofu", "shrimp": "hearts of palm",
                   "sausage": "veggie sausage", "meat": "beans", "turkey": "tofu"},
    "eggs": {"egg": "flax egg"},
}
SUBS["vegan"] = dict(SUBS["vegetarian"], **SUBS["dairy"], **SUBS["eggs"])

# spoken phrasing -> canonical restriction key
_CANON = {
    "nut": "nuts", "nuts": "nuts", "peanut": "nuts", "tree nut": "nuts",
    "gluten": "gluten", "wheat": "gluten", "celiac": "gluten", "coeliac": "gluten",
    "dairy": "dairy", "lactose": "dairy",
    "egg": "eggs", "eggs": "eggs",
    "shellfish": "shellfish",
    "fish": "fish",
    "soy": "soy",
    "pork": "pork",
    "vegetarian": "vegetarian", "veggie": "vegetarian",
    "vegan": "vegan",
}


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
            """CREATE TABLE IF NOT EXISTS restrictions (
                   id          INTEGER PRIMARY KEY,
                   restriction TEXT NOT NULL UNIQUE,
                   added_at    TEXT NOT NULL)"""
        )
        c.commit()


def add(names):
    if isinstance(names, str):
        names = [names]
    init_db()
    now = datetime.datetime.now().isoformat(timespec="seconds")
    with contextlib.closing(_conn()) as c:
        for n in names:
            n = str(n).strip().lower()
            if not n:
                continue
            c.execute("INSERT OR IGNORE INTO restrictions (restriction, added_at) "
                      "VALUES (?, ?)", (n, now))
        c.commit()


def remove(names):
    if isinstance(names, str):
        names = [names]
    init_db()
    with contextlib.closing(_conn()) as c:
        for n in names:
            c.execute("DELETE FROM restrictions WHERE restriction = ?",
                      (str(n).strip().lower(),))
        c.commit()


def active():
    init_db()
    with contextlib.closing(_conn()) as c:
        return [r[0] for r in c.execute(
            "SELECT restriction FROM restrictions ORDER BY added_at, id").fetchall()]


def clear():
    init_db()
    with contextlib.closing(_conn()) as c:
        c.execute("DELETE FROM restrictions")
        c.commit()


# --- detection ------------------------------------------------------------

def _canonical(text):
    t = _norm(text)
    for phrase, key in sorted(_CANON.items(), key=lambda kv: -len(kv[0])):
        if phrase in t:
            return key
    return None


def _kw_match(keyword, ing_words):
    return {_singular(w) for w in _norm(keyword).split()} <= ing_words


def _violates(text, restriction):
    """Does an ingredient/substitute text violate a restriction?"""
    iw = _words(text)
    return any(_kw_match(k, iw) for k in RULES.get(restriction, []))


def _sub_for(restriction, keyword, actives):
    sub = SUBS.get(restriction, {}).get(keyword)
    # only reject the sub if it breaks a DIFFERENT active restriction — its own
    # descriptive name ("soy cream", "oat milk") will trip its origin restriction.
    if sub and any(_violates(sub, r) for r in actives if r != restriction):
        return None
    return sub


def check(ingredients_str):
    """Return violations of the ACTIVE restrictions in a recipe's ingredients:
    a list of {restriction, ingredient, keyword, sub}."""
    actives = active()
    if not actives:
        return []
    out = []
    for ing in ingredients_str.split(","):
        ing = ing.strip()
        if not ing:
            continue
        iw = _words(ing)
        for r in actives:
            kw = next((k for k in sorted(RULES.get(r, []), key=len, reverse=True)
                       if _kw_match(k, iw)), None)
            if kw:
                out.append({"restriction": r, "ingredient": ing,
                            "keyword": kw, "sub": _sub_for(r, kw, actives)})
    return out


def warning(recipe):
    """Spoken heads-up for a recipe that violates active restrictions (with
    substitutions and a label caution), or "" when clean."""
    v = check(recipe.get("ingredients", ""))
    if not v:
        return ""
    restr = sorted({x["restriction"] for x in v})
    subs, seen = [], set()
    for x in v:
        if x["sub"] and x["keyword"] not in seen:
            subs.append(f"{x['sub']} instead of the {x['keyword']}")
            seen.add(x["keyword"])
    noun = "restriction" if len(restr) == 1 else "restrictions"
    msg = (f"Heads up — {recipe.get('title', 'this recipe')} conflicts with your "
           + _join(restr) + f" {noun}.")
    if subs:
        msg += " Try " + _join(subs) + "."
    return msg + " For a real allergy, double-check the labels."


def prompt_clause():
    """A clause for the suggestion prompt so the LLM avoids active restrictions."""
    a = active()
    if not a:
        return ""
    return f"I follow these dietary restrictions: {', '.join(a)}. Do not suggest recipes containing them. "


# --- voice commands -------------------------------------------------------

def answer_list():
    a = active()
    if not a:
        return "You haven't set any dietary restrictions."
    return "Your restrictions are " + _join(a) + "."


def set_from_text(text):
    key = _canonical(text)
    if key:
        add([key])
    return key


def remove_from_text(text):
    key = _canonical(text)
    if key:
        remove([key])
    return key


def handle(text):
    """Dispatch a dietary voice command: clear / remove / list / set."""
    t = _norm(text)
    if "clear" in t or "remove all" in t or "no restriction" in t:
        clear()
        return "Okay, I've cleared your dietary restrictions."
    if "remove" in t or "can eat" in t or "no longer" in t or "not allergic" in t:
        key = _canonical(text)
        if key:
            remove([key])
            return f"Okay, I've removed {key} from your restrictions."
        return "Which restriction should I remove?"
    if "what" in t or "list" in t or "my restriction" in t:
        return answer_list()
    key = _canonical(text)
    if key:
        add([key])
        return f"Got it — I'll keep your {key} restriction in mind."
    return "I'm not sure which restriction you mean."

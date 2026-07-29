# Nutritional Tracking — Phase A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give John Whisk offline calorie/macro awareness for a recipe or a food on demand ("how many calories in chicken alfredo", "how much protein in two eggs").

**Architecture:** A curated committed nutrition seed (`data/nutrition.json`, USDA-derived, public domain) loads into a `nutrition_foods` table. A new `nutrition.py` engine parses an ingredient line, looks the food up, converts the amount to grams, and computes macros; unresolved ad-hoc foods fall back to a flagged llama3.2 estimate. A `nutrition_query` router intent answers spoken questions, and computed per-serving recipe nutrition is cached on the recipe row.

**Tech Stack:** Python 3, SQLite, Ollama (llama3.2), pytest. Same conventions as the existing `restrictions.py`/`recipes.py` modules.

**Conventions (match the codebase):**
- Modules use `contextlib.closing(sqlite3.connect(config.DB_PATH))`, an `init_db()` that `CREATE TABLE IF NOT EXISTS`, and `datetime.now().isoformat(timespec="seconds")`.
- Reference/user state (nutrition table) lives in `config.DB_PATH` (`john_whisk.db`). Recipe cache lives in `config.RECIPES_DB_PATH`.
- Tests run on the Pi: `cd ~/john-whisk && venv/bin/python -m pytest <path> -q`. Deploy edits by scp from the local mirror `C:\Users\nicho\john-whisk-work` to `ngiusti@192.168.88.12:~/john-whisk/`.
- Nutrition tests monkeypatch `config.DB_PATH` to a temp file (conftest leaves `DB_PATH` alone) and monkeypatch `config.NUTRITION_SEED_PATH` to a small fixture file so tests don't depend on the shipped seed.
- LLM is always mocked in tests (`monkeypatch.setattr(nutrition.llm, "estimate_nutrition", ...)`).

**Files:**
- Create: `john_whisk/nutrition.py` — the engine + store.
- Create: `data/nutrition.json` — committed seed.
- Modify: `john_whisk/config.py` — seed path, default servings, estimate prompt.
- Modify: `john_whisk/llm.py` — `estimate_nutrition`.
- Modify: `john_whisk/recipes.py` — nutrition cache columns + get/set.
- Modify: `john_whisk/router.py` — `nutrition_query` intent.
- Modify: `john_whisk/main.py` — dispatch the intent.
- Create: `tests/test_nutrition.py`, `tests/test_nutrition_query.py`.
- Modify: `tests/test_recipes.py` — cache get/set test.

---

## Task 1: Config constants

**Files:**
- Modify: `john_whisk/config.py` (append near the other Phase 2 blocks)

- [ ] **Step 1: Add constants**

Append to `john_whisk/config.py`:

```python
# --- Nutrition (Phase 2) ---
NUTRITION_SEED_PATH = os.path.join(HOME, "john-whisk/data/nutrition.json")
DEFAULT_SERVINGS = 4          # assumed servings when a recipe states none
NUTRITION_ESTIMATE_PROMPT = (
    "Estimate the nutrition for the food described by the user. Respond with ONLY "
    'JSON of the form {"calories": <number>, "protein": <grams>, "carbs": <grams>, '
    '"fat": <grams>} for the ENTIRE amount described, using typical values. '
    "Numbers only, no units in the values, and no text before or after the JSON."
)
```

- [ ] **Step 2: Commit**

```bash
git add john_whisk/config.py
git commit -m "feat(nutrition): add config constants"
```

---

## Task 2: Nutrition seed data

**Files:**
- Create: `data/nutrition.json`

- [ ] **Step 1: Write the seed file**

Create `data/nutrition.json`. Each entry has `name`, `aliases`, `per_100g` (calories/protein/carbs/fat), and `portions` (household unit → grams; include `"each"` for count foods). Values are typical USDA per-100g figures. Include this starter set (extend later via the build script in Task 12):

```json
[
  {"name": "rice", "aliases": ["white rice", "cooked rice"], "per_100g": {"calories": 130, "protein": 2.7, "carbs": 28, "fat": 0.3}, "portions": {"cup": 158}},
  {"name": "lentils", "aliases": ["lentil", "brown lentils", "red lentils"], "per_100g": {"calories": 116, "protein": 9, "carbs": 20, "fat": 0.4}, "portions": {"cup": 198}},
  {"name": "pasta", "aliases": ["spaghetti", "penne", "macaroni", "noodles"], "per_100g": {"calories": 158, "protein": 6, "carbs": 31, "fat": 0.9}, "portions": {"cup": 140}},
  {"name": "chicken", "aliases": ["chicken breast", "chicken thigh"], "per_100g": {"calories": 165, "protein": 31, "carbs": 0, "fat": 3.6}, "portions": {"cup": 140, "breast": 174}},
  {"name": "egg", "aliases": ["eggs"], "per_100g": {"calories": 143, "protein": 12.6, "carbs": 0.7, "fat": 9.5}, "portions": {"each": 50, "large": 50, "medium": 44}},
  {"name": "milk", "aliases": ["whole milk"], "per_100g": {"calories": 61, "protein": 3.2, "carbs": 4.8, "fat": 3.3}, "portions": {"cup": 244}},
  {"name": "butter", "aliases": [], "per_100g": {"calories": 717, "protein": 0.9, "carbs": 0.1, "fat": 81}, "portions": {"cup": 227, "tablespoon": 14, "tbsp": 14, "stick": 113}},
  {"name": "olive oil", "aliases": ["oil"], "per_100g": {"calories": 884, "protein": 0, "carbs": 0, "fat": 100}, "portions": {"cup": 216, "tablespoon": 14, "tbsp": 14, "teaspoon": 4.5, "tsp": 4.5}},
  {"name": "flour", "aliases": ["all purpose flour", "wheat flour"], "per_100g": {"calories": 364, "protein": 10, "carbs": 76, "fat": 1}, "portions": {"cup": 120}},
  {"name": "sugar", "aliases": ["white sugar", "granulated sugar"], "per_100g": {"calories": 387, "protein": 0, "carbs": 100, "fat": 0}, "portions": {"cup": 200, "tablespoon": 12, "tbsp": 12, "teaspoon": 4, "tsp": 4}},
  {"name": "cream", "aliases": ["heavy cream"], "per_100g": {"calories": 340, "protein": 2.8, "carbs": 2.8, "fat": 36}, "portions": {"cup": 238, "tablespoon": 15, "tbsp": 15}},
  {"name": "parmesan", "aliases": ["parmesan cheese"], "per_100g": {"calories": 431, "protein": 38, "carbs": 4, "fat": 29}, "portions": {"cup": 100, "tablespoon": 5, "tbsp": 5}},
  {"name": "cheese", "aliases": ["cheddar", "mozzarella"], "per_100g": {"calories": 402, "protein": 25, "carbs": 1.3, "fat": 33}, "portions": {"cup": 113, "slice": 28}},
  {"name": "onion", "aliases": ["onions"], "per_100g": {"calories": 40, "protein": 1.1, "carbs": 9.3, "fat": 0.1}, "portions": {"each": 110, "cup": 160}},
  {"name": "tomato", "aliases": ["tomatoes"], "per_100g": {"calories": 18, "protein": 0.9, "carbs": 3.9, "fat": 0.2}, "portions": {"each": 123, "cup": 180}},
  {"name": "potato", "aliases": ["potatoes"], "per_100g": {"calories": 77, "protein": 2, "carbs": 17, "fat": 0.1}, "portions": {"each": 173, "cup": 150}},
  {"name": "banana", "aliases": ["bananas"], "per_100g": {"calories": 89, "protein": 1.1, "carbs": 23, "fat": 0.3}, "portions": {"each": 118, "cup": 150}},
  {"name": "bread", "aliases": ["white bread", "toast"], "per_100g": {"calories": 265, "protein": 9, "carbs": 49, "fat": 3.2}, "portions": {"slice": 28, "each": 28}},
  {"name": "chickpeas", "aliases": ["chickpea", "garbanzo"], "per_100g": {"calories": 164, "protein": 8.9, "carbs": 27, "fat": 2.6}, "portions": {"cup": 164, "can": 240}},
  {"name": "beef", "aliases": ["ground beef"], "per_100g": {"calories": 250, "protein": 26, "carbs": 0, "fat": 15}, "portions": {"cup": 140}}
]
```

- [ ] **Step 2: Commit**

```bash
git add data/nutrition.json
git commit -m "feat(nutrition): add curated nutrition seed"
```

---

## Task 3: Store — init_db, seed load, lookup

**Files:**
- Create: `john_whisk/nutrition.py`
- Test: `tests/test_nutrition.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_nutrition.py`:

```python
import json
from john_whisk import config, nutrition


def _fixture_seed(tmp_path, monkeypatch):
    """Isolate the nutrition DB + point the seed at a small fixture."""
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "n.db"))
    seed = tmp_path / "nutrition.json"
    seed.write_text(json.dumps([
        {"name": "egg", "aliases": ["eggs"],
         "per_100g": {"calories": 143, "protein": 12.6, "carbs": 0.7, "fat": 9.5},
         "portions": {"each": 50, "large": 50}},
        {"name": "rice", "aliases": ["white rice"],
         "per_100g": {"calories": 130, "protein": 2.7, "carbs": 28, "fat": 0.3},
         "portions": {"cup": 158}},
    ]))
    monkeypatch.setattr(config, "NUTRITION_SEED_PATH", str(seed))


def test_lookup_by_name(tmp_path, monkeypatch):
    _fixture_seed(tmp_path, monkeypatch)
    r = nutrition.lookup("rice")
    assert r["per_100g"]["calories"] == 130
    assert r["portions"]["cup"] == 158


def test_lookup_by_alias_and_plural(tmp_path, monkeypatch):
    _fixture_seed(tmp_path, monkeypatch)
    assert nutrition.lookup("eggs")["per_100g"]["protein"] == 12.6      # alias/plural


def test_lookup_word_subset(tmp_path, monkeypatch):
    _fixture_seed(tmp_path, monkeypatch)
    assert nutrition.lookup("cooked white rice") is not None            # entry words ⊆ query


def test_lookup_miss_returns_none(tmp_path, monkeypatch):
    _fixture_seed(tmp_path, monkeypatch)
    assert nutrition.lookup("saffron") is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/python -m pytest tests/test_nutrition.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'john_whisk.nutrition'`

- [ ] **Step 3: Write the store + lookup**

Create `john_whisk/nutrition.py`:

```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `venv/bin/python -m pytest tests/test_nutrition.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add john_whisk/nutrition.py tests/test_nutrition.py
git commit -m "feat(nutrition): store, seed load, and food lookup"
```

---

## Task 4: parse_ingredient

**Files:**
- Modify: `john_whisk/nutrition.py`
- Test: `tests/test_nutrition.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_nutrition.py`:

```python
import pytest


@pytest.mark.parametrize("line,qty,unit,food", [
    ("1 cup uncooked rice", 1.0, "cup", "uncooked rice"),
    ("2 eggs", 2.0, None, "eggs"),
    ("1/2 cup sugar", 0.5, "cup", "sugar"),
    ("1 1/2 cups flour", 1.5, "cup", "flour"),
    ("½ cup butter", 0.5, "cup", "butter"),
    ("2 tablespoons olive oil", 2.0, "tablespoon", "olive oil"),
    ("a pinch of salt", 1.0, "pinch", "salt"),
    ("salt to taste", None, None, "salt to taste"),
])
def test_parse_ingredient(line, qty, unit, food):
    assert nutrition.parse_ingredient(line) == (qty, unit, food)
```

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/python -m pytest tests/test_nutrition.py -k parse_ingredient -q`
Expected: FAIL — `AttributeError: module ... has no attribute 'parse_ingredient'`

- [ ] **Step 3: Implement parse_ingredient**

Add to `john_whisk/nutrition.py`:

```python
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
        return int(n) / int(d), tokens[1:]
    if re.fullmatch(r"\d+(\.\d+)?", t0):
        val = float(t0)
        if len(tokens) > 1 and re.fullmatch(r"\d+/\d+", tokens[1]):   # mixed "1 1/2"
            n, d = tokens[1].split("/")
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `venv/bin/python -m pytest tests/test_nutrition.py -k parse_ingredient -q`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add john_whisk/nutrition.py tests/test_nutrition.py
git commit -m "feat(nutrition): deterministic ingredient parsing"
```

---

## Task 5: to_grams

**Files:**
- Modify: `john_whisk/nutrition.py`
- Test: `tests/test_nutrition.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_nutrition.py`:

```python
def test_to_grams_food_portion(tmp_path, monkeypatch):
    _fixture_seed(tmp_path, monkeypatch)
    assert nutrition.to_grams(1, "cup", "rice") == 158           # food's own portion


def test_to_grams_count_each(tmp_path, monkeypatch):
    _fixture_seed(tmp_path, monkeypatch)
    assert nutrition.to_grams(2, None, "eggs") == 100            # 2 * each(50)


def test_to_grams_mass_unit(tmp_path, monkeypatch):
    _fixture_seed(tmp_path, monkeypatch)
    assert nutrition.to_grams(200, "gram", "rice") == 200        # direct mass


def test_to_grams_generic_volume(tmp_path, monkeypatch):
    _fixture_seed(tmp_path, monkeypatch)
    # no "tablespoon" portion for rice -> generic approximation (15 g)
    assert nutrition.to_grams(2, "tablespoon", "rice") == 30


def test_to_grams_unconvertible(tmp_path, monkeypatch):
    _fixture_seed(tmp_path, monkeypatch)
    assert nutrition.to_grams(1, "pinch", "rice") is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/python -m pytest tests/test_nutrition.py -k to_grams -q`
Expected: FAIL — no attribute `to_grams`

- [ ] **Step 3: Implement to_grams**

Add to `john_whisk/nutrition.py`:

```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `venv/bin/python -m pytest tests/test_nutrition.py -k to_grams -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add john_whisk/nutrition.py tests/test_nutrition.py
git commit -m "feat(nutrition): unit-to-grams conversion"
```

---

## Task 6: LLM fallback — llm.estimate_nutrition

**Files:**
- Modify: `john_whisk/llm.py`
- Test: `tests/test_nutrition.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_nutrition.py` (mocks Ollama at the `requests` layer, matching how `llm` is structured):

```python
from john_whisk import llm


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_estimate_nutrition_parses_json(monkeypatch):
    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: _Resp(
        {"response": '{"calories": 200, "protein": 6, "carbs": 30, "fat": 5}'}))
    out = llm.estimate_nutrition("one bagel")
    assert out == {"calories": 200.0, "protein": 6.0, "carbs": 30.0, "fat": 5.0}


def test_estimate_nutrition_failure_returns_none(monkeypatch):
    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: _Resp({"response": "nope"}))
    assert llm.estimate_nutrition("one bagel") is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/python -m pytest tests/test_nutrition.py -k estimate_nutrition -q`
Expected: FAIL — no attribute `estimate_nutrition`

- [ ] **Step 3: Implement estimate_nutrition**

Add to `john_whisk/llm.py` (mirrors `extract_items`' JSON-mode call):

```python
def estimate_nutrition(food_text):
    """Ask the LLM to estimate {calories, protein, carbs, fat} (all floats) for a
    food/amount the local table can't cover. Returns None on failure or if any
    field is missing/non-numeric. Numbers are rough estimates."""
    if not food_text or not food_text.strip():
        return None
    payload = {
        "model": config.OLLAMA_MODEL,
        "prompt": food_text,
        "system": config.NUTRITION_ESTIMATE_PROMPT,
        "stream": False,
        "format": "json",
        "options": {"num_ctx": config.NUM_CTX, "num_predict": config.NUM_PREDICT},
    }
    try:
        r = requests.post(config.OLLAMA_URL, json=payload, timeout=config.OLLAMA_TIMEOUT)
        r.raise_for_status()
        data = json.loads(r.json().get("response", ""))
    except (requests.RequestException, ValueError, TypeError):
        return None
    out = {}
    for key in ("calories", "protein", "carbs", "fat"):
        v = data.get(key)
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            return None
        out[key] = float(v)
    return out
```

- [ ] **Step 4: Run to verify it passes**

Run: `venv/bin/python -m pytest tests/test_nutrition.py -k estimate_nutrition -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add john_whisk/llm.py tests/test_nutrition.py
git commit -m "feat(nutrition): LLM nutrition estimate fallback"
```

---

## Task 7: for_food (local + fallback)

**Files:**
- Modify: `john_whisk/nutrition.py`
- Test: `tests/test_nutrition.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_nutrition.py`:

```python
def test_for_food_local(tmp_path, monkeypatch):
    _fixture_seed(tmp_path, monkeypatch)
    out = nutrition.for_food(2, None, "eggs")           # 100 g -> per_100g * 1.0
    assert out["calories"] == 143 and out["protein"] == pytest.approx(12.6)
    assert out["estimated"] is False


def test_for_food_scales_by_grams(tmp_path, monkeypatch):
    _fixture_seed(tmp_path, monkeypatch)
    out = nutrition.for_food(1, "cup", "rice")          # 158 g -> 1.58 * per_100g
    assert out["calories"] == pytest.approx(130 * 1.58)
    assert out["estimated"] is False


def test_for_food_falls_back_to_llm(tmp_path, monkeypatch):
    _fixture_seed(tmp_path, monkeypatch)
    monkeypatch.setattr(nutrition.llm, "estimate_nutrition",
                        lambda text: {"calories": 250, "protein": 9, "carbs": 40, "fat": 6})
    out = nutrition.for_food(1, None, "bagel")          # not in the table
    assert out["calories"] == 250 and out["estimated"] is True


def test_for_food_no_data_returns_none(tmp_path, monkeypatch):
    _fixture_seed(tmp_path, monkeypatch)
    monkeypatch.setattr(nutrition.llm, "estimate_nutrition", lambda text: None)
    assert nutrition.for_food(1, None, "unobtainium") is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/python -m pytest tests/test_nutrition.py -k for_food -q`
Expected: FAIL — no attribute `for_food`

- [ ] **Step 3: Implement for_food**

Add to `john_whisk/nutrition.py`:

```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `venv/bin/python -m pytest tests/test_nutrition.py -k for_food -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add john_whisk/nutrition.py tests/test_nutrition.py
git commit -m "feat(nutrition): per-food nutrition with LLM fallback"
```

---

## Task 8: for_recipe

**Files:**
- Modify: `john_whisk/nutrition.py`
- Test: `tests/test_nutrition.py`

Note: `for_recipe` sums LOCAL matches only (keeps the slow 3B off the per-ingredient hot path) and surfaces `unmatched` ingredients; `estimated=True` when anything was unmatched.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_nutrition.py`:

```python
def test_for_recipe_sums_and_divides(tmp_path, monkeypatch):
    _fixture_seed(tmp_path, monkeypatch)
    recipe = {"title": "Egg Rice", "ingredients": "2 eggs, 1 cup rice",
              "steps": ["a", "b"]}
    out = nutrition.for_recipe(recipe, servings=2)
    # eggs: 100 g -> 143 cal ; rice: 158 g -> 130*1.58 = 205.4 cal ; total ~348.4
    assert out["total"]["calories"] == pytest.approx(143 + 130 * 1.58, abs=0.5)
    assert out["per_serving"]["calories"] == pytest.approx(out["total"]["calories"] / 2, abs=0.5)
    assert out["unmatched"] == []
    assert out["estimated"] is False


def test_for_recipe_reports_unmatched(tmp_path, monkeypatch):
    _fixture_seed(tmp_path, monkeypatch)
    recipe = {"title": "Fancy", "ingredients": "1 cup rice, 1 pinch saffron",
              "steps": ["a"]}
    out = nutrition.for_recipe(recipe, servings=1)
    assert "1 pinch saffron" in out["unmatched"]
    assert out["estimated"] is True


def test_for_recipe_default_servings(tmp_path, monkeypatch):
    _fixture_seed(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "DEFAULT_SERVINGS", 4)
    recipe = {"title": "Rice", "ingredients": "4 cups rice", "steps": ["a"]}
    out = nutrition.for_recipe(recipe)          # no servings -> DEFAULT_SERVINGS
    assert out["per_serving"]["calories"] == pytest.approx(out["total"]["calories"] / 4, abs=0.5)
```

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/python -m pytest tests/test_nutrition.py -k for_recipe -q`
Expected: FAIL — no attribute `for_recipe`

- [ ] **Step 3: Implement for_recipe**

Add to `john_whisk/nutrition.py`:

```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `venv/bin/python -m pytest tests/test_nutrition.py -k for_recipe -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add john_whisk/nutrition.py tests/test_nutrition.py
git commit -m "feat(nutrition): per-recipe nutrition summation"
```

---

## Task 9: describe (spoken sentence)

**Files:**
- Modify: `john_whisk/nutrition.py`
- Test: `tests/test_nutrition.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_nutrition.py`:

```python
def test_describe_sentence():
    s = nutrition.describe({"calories": 620.4, "protein": 34, "carbs": 45, "fat": 32},
                           per_serving=True)
    assert "620 calories" in s and "a serving" in s
    assert "34 g protein" in s and "45 g carbs" in s and "32 g fat" in s


def test_describe_estimate_flag():
    s = nutrition.describe({"calories": 200, "protein": 6, "carbs": 30, "fat": 5},
                           per_serving=False, estimated=True)
    assert "roughly" in s.lower() or "estimate" in s.lower()
```

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/python -m pytest tests/test_nutrition.py -k describe -q`
Expected: FAIL — no attribute `describe`

- [ ] **Step 3: Implement describe**

Add to `john_whisk/nutrition.py`:

```python
def describe(nutr, per_serving=True, estimated=False):
    """A short spoken nutrition sentence from a macro dict."""
    where = "a serving" if per_serving else "that"
    lead = "Roughly " if estimated else "About "
    return (f"{lead}{round(nutr['calories'])} calories {where}: "
            f"{round(nutr['protein'])} g protein, {round(nutr['carbs'])} g carbs, "
            f"{round(nutr['fat'])} g fat.")
```

- [ ] **Step 4: Run to verify it passes**

Run: `venv/bin/python -m pytest tests/test_nutrition.py -k describe -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add john_whisk/nutrition.py tests/test_nutrition.py
git commit -m "feat(nutrition): spoken description helper"
```

---

## Task 10: Recipe nutrition cache

**Files:**
- Modify: `john_whisk/recipes.py`
- Test: `tests/test_recipes.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_recipes.py`:

```python
def test_nutrition_cache_roundtrip(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    recipes.add_recipe(*ALFREDO)
    assert recipes.get_nutrition("Chicken Alfredo") is None       # nothing cached yet
    recipes.set_nutrition("Chicken Alfredo",
                          {"calories": 620, "protein": 34, "carbs": 45, "fat": 32})
    cached = recipes.get_nutrition("chicken alfredo")             # norm-title match
    assert cached == {"calories": 620.0, "protein": 34.0, "carbs": 45.0, "fat": 32.0}
```

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/python -m pytest tests/test_recipes.py -k nutrition_cache -q`
Expected: FAIL — no attribute `get_nutrition`

- [ ] **Step 3: Implement the cache**

In `john_whisk/recipes.py`, extend `init_db()` to add the columns via a guarded migration (SQLite has no `ADD COLUMN IF NOT EXISTS`; check `PRAGMA table_info`). Add after the existing `CREATE TABLE` in `init_db`:

```python
        cols = {r[1] for r in c.execute("PRAGMA table_info(recipes)").fetchall()}
        for col in ("cal", "protein", "carbs", "fat"):
            if col not in cols:
                c.execute(f"ALTER TABLE recipes ADD COLUMN {col} REAL")
        c.commit()
```

Then add these functions to `john_whisk/recipes.py`:

```python
def get_nutrition(title):
    """Cached per-serving macros for a recipe (by normalized title), or None if
    not yet computed."""
    init_db()
    tn = _norm(title)
    with contextlib.closing(_conn()) as c:
        row = c.execute("SELECT cal, protein, carbs, fat FROM recipes "
                        "WHERE title_norm = ?", (tn,)).fetchone()
    if not row or row[0] is None:
        return None
    return {"calories": row[0], "protein": row[1], "carbs": row[2], "fat": row[3]}


def set_nutrition(title, nutr):
    """Cache per-serving macros on the recipe row (by normalized title)."""
    init_db()
    tn = _norm(title)
    with contextlib.closing(_conn()) as c:
        c.execute("UPDATE recipes SET cal = ?, protein = ?, carbs = ?, fat = ? "
                  "WHERE title_norm = ?",
                  (float(nutr["calories"]), float(nutr["protein"]),
                   float(nutr["carbs"]), float(nutr["fat"]), tn))
        c.commit()
```

- [ ] **Step 4: Run to verify it passes**

Run: `venv/bin/python -m pytest tests/test_recipes.py -k nutrition_cache -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add john_whisk/recipes.py tests/test_recipes.py
git commit -m "feat(nutrition): cache per-serving nutrition on recipes"
```

---

## Task 11: answer_query + router intent + dispatch

**Files:**
- Modify: `john_whisk/nutrition.py`
- Modify: `john_whisk/router.py`
- Modify: `john_whisk/main.py`
- Test: `tests/test_nutrition.py`, `tests/test_nutrition_query.py`

- [ ] **Step 1: Write the failing test for answer_query**

Append to `tests/test_nutrition.py`:

```python
def test_answer_query_stored_recipe(tmp_path, monkeypatch):
    _fixture_seed(tmp_path, monkeypatch)
    from john_whisk import recipes
    monkeypatch.setattr(config, "RECIPES_DB_PATH", str(tmp_path / "r.db"))
    recipes.add_recipe("Egg Rice", "2 eggs, 1 cup rice", ["a", "b"])
    reply = nutrition.answer_query("how many calories in egg rice")
    assert "calories" in reply.lower() and "serving" in reply.lower()
    assert recipes.get_nutrition("Egg Rice") is not None          # cached on first ask


def test_answer_query_ad_hoc_food(tmp_path, monkeypatch):
    _fixture_seed(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "RECIPES_DB_PATH", str(tmp_path / "r.db"))
    reply = nutrition.answer_query("how many calories in two eggs")
    assert "143" in reply or "calories" in reply.lower()
```

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/python -m pytest tests/test_nutrition.py -k answer_query -q`
Expected: FAIL — no attribute `answer_query`

- [ ] **Step 3: Implement answer_query**

Add to `john_whisk/nutrition.py` (top-level import stays `from john_whisk import config, llm`; import `recipes` lazily inside to avoid a heavy import cycle, matching how `cooking` imports peers):

```python
_QUERY_LEADINS = [
    "how many calories are in", "how many calories in", "how much protein in",
    "how much fat in", "how many carbs in", "how many carbs are in",
    "calories in", "macros in", "macros for", "nutrition in", "nutrition for",
    "nutrition facts for", "calories for", "how many calories does", "in",
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
    subject = _subject(text)
    if not subject:
        return "Which food or recipe do you want the nutrition for?"
    recipe = recipes.find(subject)
    if recipe:
        cached = recipes.get_nutrition(recipe["title"])
        if cached:
            return f"{recipe['title']}: " + describe(cached, per_serving=True)
        result = for_recipe(recipe)
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `venv/bin/python -m pytest tests/test_nutrition.py -k answer_query -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Write the failing router test**

Create `tests/test_nutrition_query.py`:

```python
from john_whisk import router


def test_nutrition_query_classified():
    assert router.classify("how many calories in chicken alfredo") == "nutrition_query"
    assert router.classify("what are the macros in two eggs") == "nutrition_query"
    assert router.classify("nutrition facts for pad thai") == "nutrition_query"


def test_nutrition_query_does_not_shadow_recipe_query():
    assert router.classify("how many recipes do you have") == "recipe_query"


def test_nutrition_query_does_not_shadow_cook():
    assert router.classify("let's make chicken alfredo") == "cook"
```

- [ ] **Step 6: Run to verify it fails**

Run: `venv/bin/python -m pytest tests/test_nutrition_query.py -q`
Expected: FAIL — classify returns "general" for the nutrition lines

- [ ] **Step 7: Add the router intent**

In `john_whisk/router.py`, add the trigger list near the other trigger constants:

```python
# Nutrition questions about a recipe or food. After recipe_query (so "how many
# recipes" stays a library query) and after cook; before general.
NUTRITION_QUERY_TRIGGERS = [
    "calories", "macros", "how much protein", "how much fat", "how many carbs",
    "nutrition", "nutritional",
]
```

In `classify()`, insert the check immediately AFTER the `recipe_query` check and BEFORE `plan`:

```python
    if any(k in t for k in RECIPE_QUERY_TRIGGERS):
        return "recipe_query"
    if any(k in t for k in NUTRITION_QUERY_TRIGGERS):
        return "nutrition_query"
```

Also update the `classify` docstring's precedence list to include `nutrition_query` after `recipe_query`.

- [ ] **Step 8: Run to verify it passes**

Run: `venv/bin/python -m pytest tests/test_nutrition_query.py -q`
Expected: PASS (3 passed)

- [ ] **Step 9: Wire dispatch in main.py**

In `john_whisk/main.py`, add `nutrition` to the big `from john_whisk import ...` line, and add this dispatch branch right after the `recipe_query` branch in `process_utterance`:

```python
    if intent == "nutrition_query":
        return nutrition.answer_query(text)
```

- [ ] **Step 10: Commit**

```bash
git add john_whisk/nutrition.py john_whisk/router.py john_whisk/main.py tests/test_nutrition.py tests/test_nutrition_query.py
git commit -m "feat(nutrition): nutrition_query intent and dispatch"
```

---

## Task 12: Full suite, on-device smoke test, and seed-builder note

**Files:**
- Create: `scripts/build_nutrition_seed.py` (documented stub for later expansion)

- [ ] **Step 1: Run the full deterministic suite**

Run: `venv/bin/python -m pytest -q --ignore=tests/test_extract.py --ignore=tests/test_stt.py`
Expected: PASS — all prior tests plus the new nutrition tests, no regressions.

- [ ] **Step 2: On-device smoke test (real seed, real recipe library)**

Run on the Pi:

```bash
cd ~/john-whisk && venv/bin/python -c "
from john_whisk import nutrition
print(nutrition.answer_query('how many calories in two eggs'))
print(nutrition.answer_query('calories in koshari'))
"
```
Expected: two sensible spoken sentences (eggs ~143 cal; koshari a per-serving figure, possibly noting unmatched spices).

- [ ] **Step 3: Add the seed-builder stub**

Create `scripts/build_nutrition_seed.py`:

```python
"""Regenerate/extend data/nutrition.json from USDA FoodData Central (public
domain). NOT run at runtime. Download the SR Legacy CSV bundle from
https://fdc.nal.usda.gov/download-datasets.html, then for each curated common
food pull its per-100g calories/protein/carbs/fat from food_nutrient.csv and
household weights from food_portion.csv, and write the JSON shape used by
data/nutrition.json (see nutrition._load_seed). Left as a documented maintainer
tool; the hand-curated seed already ships with the app."""

if __name__ == "__main__":
    raise SystemExit("Maintainer tool: see module docstring; not yet implemented.")
```

- [ ] **Step 4: Commit**

```bash
git add scripts/build_nutrition_seed.py
git commit -m "docs(nutrition): seed-builder stub for later expansion"
```

---

## Self-Review notes

- **Spec coverage (Phase A):** seed + `nutrition_foods` (Tasks 2–3), `parse_ingredient` (4), `lookup` (3), `to_grams` (5), `for_food` (7), `for_recipe` (8), `describe` (9), LLM fallback (6), `nutrition_query` for recipe & food (11), recipe caching (10). Phase B (daily log/goals) and Phase C (dashboard) are intentionally out of this plan.
- **Deferred within Phase A (documented, not silent):** per-ingredient LLM fallback inside `for_recipe` is deferred — unmatched ingredients are surfaced and flagged instead, to keep the slow 3B off the summation path. The USDA bulk seed-builder is a stub (Task 12); the hand-curated seed ships now.
- **Type consistency:** macro dicts always use keys `calories/protein/carbs/fat`; `for_food`/`for_recipe` add `estimated`; `describe` reads `calories/protein/carbs/fat`; cache stores per-serving macros. `lookup` returns `{name, aliases, per_100g, portions}`. Names match across tasks.

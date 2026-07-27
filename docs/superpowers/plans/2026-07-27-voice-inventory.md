# Voice Inventory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give John Whisk a voice-tracked pantry: "I bought two chicken breasts and a dozen eggs" stores items with quantities; "what can I make?" suggests recipes from stock.

**Architecture:** A keyword router classifies each transcript (add / suggest / general). `add` uses the LLM to extract items+quantities into SQLite; `suggest` reads stock and asks the LLM for flexible recipe ideas; `general` keeps today's `llm.ask` path. New modules `db`, `router`, `inventory`; small additions to `llm` and `main`.

**Tech Stack:** Python 3.13, stdlib `sqlite3`, Ollama (`llama3.2:3b`) JSON mode, pytest. Runs in the existing `~/john-whisk` repo/venv on the Pi.

**Working context:** All work on the Pi at `~/john-whisk` (git repo, venv). Develop over SSH: `ssh ngiusti@192.168.88.12`. Run pytest with `./venv/bin/python -m pytest`. The `john-whisk.service` runs the live app; restart it (`sudo systemctl restart john-whisk`) only for the final live test.

---

## File Structure

| File | Responsibility |
|---|---|
| `john_whisk/config.py` (edit) | Add `DB_PATH` and `EXTRACT_PROMPT`. |
| `john_whisk/db.py` (new) | SQLite: `init_db()`, `add_items(items)`, `get_inventory()`. Merge-on-add by name. |
| `john_whisk/router.py` (new) | `classify(text) -> "add"\|"suggest"\|"general"` by keyword, precedence suggest→add→general. |
| `john_whisk/llm.py` (edit) | Add `extract_items(text) -> list[dict]` (Ollama JSON mode). Keep `ask()`. |
| `john_whisk/inventory.py` (new) | `add_from_text(text) -> str`, `suggest(text) -> str`. Uses `db`, `llm`. |
| `john_whisk/main.py` (edit) | `handle_turn` routes via `router`; `main` calls `db.init_db()` at startup. |
| `tests/test_db.py`, `test_router.py`, `test_extract.py`, `test_inventory.py` (new) | Unit/integration tests, no hardware. |

Item shape everywhere: `{"name": str, "quantity": float|None, "unit": str|None}`.

---

## Task 1: config additions

**Files:**
- Modify: `john_whisk/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Add the failing test**

Append to `tests/test_config.py`:
```python
def test_inventory_config_present():
    assert config.DB_PATH.endswith("john_whisk.db")
    assert "json" in config.EXTRACT_PROMPT.lower()
```

- [ ] **Step 2: Run it, expect FAIL**

Run: `cd ~/john-whisk && ./venv/bin/python -m pytest tests/test_config.py::test_inventory_config_present -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'DB_PATH'`.

- [ ] **Step 3: Add config values**

Append to `john_whisk/config.py`:
```python
# --- Inventory (Phase 2) ---
DB_PATH = os.path.join(HOME, "john-whisk/john_whisk.db")

EXTRACT_PROMPT = (
    "The user just told you which groceries they bought. Extract each food item and its "
    "quantity. Respond with ONLY JSON of the form "
    '{"items": [{"name": <singular lowercase string>, "quantity": <number or null>, '
    '"unit": <string or null>}]}. Use null quantity for vague amounts like "some" or "a bit". '
    "Convert number words to digits (a dozen = 12, a couple = 2, a few = 3, half a dozen = 6)."
)
```

- [ ] **Step 4: Run it, expect PASS**

Run: `cd ~/john-whisk && ./venv/bin/python -m pytest tests/test_config.py -v`
Expected: PASS (both config tests).

- [ ] **Step 5: Commit**

```bash
cd ~/john-whisk && git add -A && git commit -m "feat(inventory): config DB_PATH + extraction prompt"
```

---

## Task 2: db.py (SQLite store)

**Files:**
- Create: `john_whisk/db.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_db.py`:
```python
from john_whisk import config, db


def test_add_and_get(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    db.add_items([{"name": "eggs", "quantity": 2, "unit": None}])
    assert db.get_inventory() == [{"name": "eggs", "quantity": 2.0, "unit": None}]


def test_merge_sums_numeric_quantities(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    db.add_items([{"name": "eggs", "quantity": 2, "unit": None}])
    db.add_items([{"name": "eggs", "quantity": 12, "unit": None}])
    inv = db.get_inventory()
    assert len(inv) == 1
    assert inv[0]["quantity"] == 14.0


def test_merge_with_vague_becomes_null(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    db.add_items([{"name": "spinach", "quantity": 2, "unit": None}])
    db.add_items([{"name": "spinach", "quantity": None, "unit": None}])
    assert db.get_inventory()[0]["quantity"] is None
```

- [ ] **Step 2: Run, expect FAIL**

Run: `cd ~/john-whisk && ./venv/bin/python -m pytest tests/test_db.py -v`
Expected: FAIL — `ImportError: cannot import name 'db'`.

- [ ] **Step 3: Write db.py**

`john_whisk/db.py`:
```python
import sqlite3
import contextlib
import datetime
from john_whisk import config


def _conn():
    return sqlite3.connect(config.DB_PATH)


def init_db():
    with contextlib.closing(_conn()) as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS inventory (
                   id       INTEGER PRIMARY KEY,
                   name     TEXT NOT NULL,
                   quantity REAL,
                   unit     TEXT,
                   added_at TEXT NOT NULL)"""
        )
        c.commit()


def add_items(items):
    """Insert items, merging by name: sum numeric quantities; vague (None) -> None."""
    init_db()
    now = datetime.datetime.now().isoformat(timespec="seconds")
    with contextlib.closing(_conn()) as c:
        for it in items:
            name = it["name"]
            qty = it.get("quantity")
            unit = it.get("unit")
            row = c.execute(
                "SELECT id, quantity FROM inventory WHERE name = ?", (name,)
            ).fetchone()
            if row:
                existing = row[1]
                merged = None if (qty is None or existing is None) else existing + qty
                c.execute(
                    "UPDATE inventory SET quantity = ?, unit = COALESCE(?, unit), added_at = ? WHERE id = ?",
                    (merged, unit, now, row[0]),
                )
            else:
                c.execute(
                    "INSERT INTO inventory (name, quantity, unit, added_at) VALUES (?, ?, ?, ?)",
                    (name, qty, unit, now),
                )
        c.commit()


def get_inventory():
    init_db()
    with contextlib.closing(_conn()) as c:
        rows = c.execute(
            "SELECT name, quantity, unit FROM inventory ORDER BY name"
        ).fetchall()
    return [{"name": r[0], "quantity": r[1], "unit": r[2]} for r in rows]
```

- [ ] **Step 4: Run, expect PASS**

Run: `cd ~/john-whisk && ./venv/bin/python -m pytest tests/test_db.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
cd ~/john-whisk && git add -A && git commit -m "feat(inventory): sqlite db module with merge-on-add"
```

---

## Task 3: router.py (intent classification)

**Files:**
- Create: `john_whisk/router.py`
- Test: `tests/test_router.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_router.py`:
```python
from john_whisk import router


def test_suggest():
    assert router.classify("What can I make for dinner?") == "suggest"


def test_add():
    assert router.classify("I bought chicken and some eggs") == "add"


def test_general():
    assert router.classify("How long should I boil an egg?") == "general"


def test_precedence_suggest_beats_add():
    assert router.classify("what can i make with the chicken i bought") == "suggest"
```

- [ ] **Step 2: Run, expect FAIL**

Run: `cd ~/john-whisk && ./venv/bin/python -m pytest tests/test_router.py -v`
Expected: FAIL — `ImportError: cannot import name 'router'`.

- [ ] **Step 3: Write router.py**

`john_whisk/router.py`:
```python
SUGGEST_TRIGGERS = [
    "what can i make", "what can i cook", "what should i", "suggest", "recipe",
    "what's for dinner", "whats for dinner", "ideas for dinner", "make with",
]
ADD_TRIGGERS = [
    "bought", "grabbed", "picked up", "purchased", "just got", "stock up",
    "i have", "we have", " got ", "add ",
]


def classify(text: str) -> str:
    """Return 'add', 'suggest', or 'general'. Precedence: suggest -> add -> general."""
    t = " " + text.lower().strip() + " "
    if any(k in t for k in SUGGEST_TRIGGERS):
        return "suggest"
    if any(k in t for k in ADD_TRIGGERS):
        return "add"
    return "general"
```

Note: `" got "` and `"add "` use surrounding spaces to avoid matching inside words
(e.g. "forgot", "additional"). The text is padded with spaces so leading/trailing
triggers still match.

- [ ] **Step 4: Run, expect PASS**

Run: `cd ~/john-whisk && ./venv/bin/python -m pytest tests/test_router.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
cd ~/john-whisk && git add -A && git commit -m "feat(inventory): keyword intent router"
```

---

## Task 4: llm.extract_items (LLM JSON extraction)

**Files:**
- Modify: `john_whisk/llm.py`
- Test: `tests/test_extract.py`

- [ ] **Step 1: Write the failing test**

`tests/test_extract.py`:
```python
from john_whisk import llm


def test_extract_items_names_and_types():
    items = llm.extract_items("I bought two chicken breasts and a dozen eggs")
    assert isinstance(items, list) and len(items) >= 2
    names = " ".join(i["name"] for i in items)
    assert "chicken" in names
    assert "egg" in names
    for i in items:
        assert i["quantity"] is None or isinstance(i["quantity"], (int, float))
        assert i["unit"] is None or isinstance(i["unit"], str)


def test_extract_items_empty_on_junk():
    # Non-grocery text should yield no items (model returns empty list).
    items = llm.extract_items("the weather is nice today")
    assert isinstance(items, list)
```

- [ ] **Step 2: Run, expect FAIL**

Run: `cd ~/john-whisk && ./venv/bin/python -m pytest tests/test_extract.py -v`
Expected: FAIL — `AttributeError: module 'john_whisk.llm' has no attribute 'extract_items'`.

- [ ] **Step 3: Add extract_items to llm.py**

Add `import json` at the top of `john_whisk/llm.py` (next to `import requests`), then append:
```python
def extract_items(text: str):
    """Ask the LLM to extract grocery items+quantities as JSON. Returns a list of
    {name, quantity, unit} dicts (normalized), or [] on any failure."""
    payload = {
        "model": config.OLLAMA_MODEL,
        "prompt": text,
        "system": config.EXTRACT_PROMPT,
        "stream": False,
        "format": "json",
        "options": {"num_ctx": config.NUM_CTX, "num_predict": config.NUM_PREDICT},
    }
    try:
        r = requests.post(config.OLLAMA_URL, json=payload, timeout=config.OLLAMA_TIMEOUT)
        r.raise_for_status()
        data = json.loads(r.json().get("response", ""))
        raw_items = data.get("items", [])
    except (requests.RequestException, ValueError, TypeError, KeyError):
        return []
    result = []
    for it in raw_items:
        if not isinstance(it, dict):
            continue
        name = it.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        qty = it.get("quantity")
        if not isinstance(qty, (int, float)) or isinstance(qty, bool):
            qty = None
        unit = it.get("unit")
        if not isinstance(unit, str) or not unit.strip():
            unit = None
        result.append({"name": name.strip().lower(), "quantity": qty, "unit": unit})
    return result
```

- [ ] **Step 4: Run, expect PASS**

Run: `cd ~/john-whisk && ./venv/bin/python -m pytest tests/test_extract.py -v`
Expected: PASS. (Integration test against live Ollama; first call may cold-load ~26s.)
If `test_extract_items_names_and_types` occasionally flakes on wording, re-run once; the assertions are intentionally lenient (substring names, type-only on quantity).

- [ ] **Step 5: Commit**

```bash
cd ~/john-whisk && git add -A && git commit -m "feat(inventory): llm.extract_items JSON extraction"
```

---

## Task 5: inventory.py (add + suggest logic)

**Files:**
- Create: `john_whisk/inventory.py`
- Test: `tests/test_inventory.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_inventory.py`:
```python
from john_whisk import config, db, llm, inventory


def test_add_from_text_stores_and_confirms(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(llm, "extract_items", lambda text: [
        {"name": "eggs", "quantity": 12, "unit": None},
        {"name": "spinach", "quantity": None, "unit": None},
    ])
    msg = inventory.add_from_text("whatever")
    assert msg.lower().startswith("added")
    assert "eggs" in msg and "spinach" in msg
    names = [i["name"] for i in db.get_inventory()]
    assert "eggs" in names and "spinach" in names


def test_add_from_text_no_items(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(llm, "extract_items", lambda text: [])
    assert "didn't catch" in inventory.add_from_text("whatever").lower()


def test_suggest_empty_pantry(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    assert "empty" in inventory.suggest("what can I make?").lower()


def test_suggest_with_stock_calls_llm(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    db.add_items([{"name": "eggs", "quantity": 12, "unit": None}])
    monkeypatch.setattr(llm, "ask", lambda prompt: "You could make an omelette.")
    reply = inventory.suggest("what can I make?")
    assert reply == "You could make an omelette."
```

- [ ] **Step 2: Run, expect FAIL**

Run: `cd ~/john-whisk && ./venv/bin/python -m pytest tests/test_inventory.py -v`
Expected: FAIL — `ImportError: cannot import name 'inventory'`.

- [ ] **Step 3: Write inventory.py**

`john_whisk/inventory.py`:
```python
from john_whisk import db, llm


def _format_item(item) -> str:
    """'2 eggs', '12 eggs', or just 'spinach' when quantity is unknown."""
    q = item["quantity"]
    name = item["name"]
    if q is None:
        return name
    q_str = str(int(q)) if float(q).is_integer() else str(q)
    return f"{q_str} {name}"


def _join(parts) -> str:
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return parts[0] + " and " + parts[1]
    return ", ".join(parts[:-1]) + ", and " + parts[-1]


def add_from_text(text: str) -> str:
    items = llm.extract_items(text)
    if not items:
        return "I didn't catch what you bought. Try again."
    db.add_items(items)
    return "Added " + _join([_format_item(i) for i in items]) + "."


def suggest(text: str) -> str:
    stock = db.get_inventory()
    if not stock:
        return "Your pantry's empty. Tell me what you bought first."
    stock_str = ", ".join(_format_item(i) for i in stock)
    prompt = (
        f"I have these items in my kitchen: {stock_str}. {text} "
        "Suggest one or two quick recipe ideas that mostly use these items. "
        "You may mention one or two common items I'd need to add."
    )
    return llm.ask(prompt) or "Sorry, my brain hiccupped. Try again."
```

- [ ] **Step 4: Run, expect PASS**

Run: `cd ~/john-whisk && ./venv/bin/python -m pytest tests/test_inventory.py -v`
Expected: PASS (4 tests; all `llm`/db calls are monkeypatched or empty-pantry, so no live Ollama needed here).

- [ ] **Step 5: Commit**

```bash
cd ~/john-whisk && git add -A && git commit -m "feat(inventory): add_from_text + suggest logic"
```

---

## Task 6: Wire into the loop (main.py)

**Files:**
- Modify: `john_whisk/main.py`

- [ ] **Step 1: Update imports**

In `john_whisk/main.py`, change the import line:
```python
from john_whisk import config, wake, audio, stt, llm, tts
```
to:
```python
from john_whisk import config, wake, audio, stt, llm, tts, router, inventory, db
```

- [ ] **Step 2: Route the transcript in `handle_turn`**

In `handle_turn`, replace this block:
```python
    reply = llm.ask(text)
    log.info("reply: %s", reply)
    print("reply:", reply, flush=True)
    if not reply.strip():
        tts.speak("Sorry, my brain hiccupped. Try again.")
        return
    tts.speak(reply)
```
with:
```python
    intent = router.classify(text)
    log.info("intent: %s", intent)
    if intent == "add":
        reply = inventory.add_from_text(text)
    elif intent == "suggest":
        reply = inventory.suggest(text)
    else:
        reply = llm.ask(text)
    log.info("reply: %s", reply)
    print("reply:", reply, flush=True)
    if not reply.strip():
        tts.speak("Sorry, my brain hiccupped. Try again.")
        return
    tts.speak(reply)
```

- [ ] **Step 3: Init the DB at startup**

In `main()`, right after `log.info("John Whisk starting up")`, add:
```python
    db.init_db()
```

- [ ] **Step 4: Verify imports wire together (no hardware)**

Run: `cd ~/john-whisk && ./venv/bin/python -c "import john_whisk.main; print('wired ok')" 2>&1 | grep -viE 'device_discovery|GetGpuDevices|ReadFileContents|pkg_resources|import pkg_resources'`
Expected: `wired ok`.

- [ ] **Step 5: Commit**

```bash
cd ~/john-whisk && git add -A && git commit -m "feat(inventory): route add/suggest/general in handle_turn"
```

---

## Task 7: Full suite + live voice test

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `cd ~/john-whisk && ./venv/bin/python -m pytest -q 2>&1 | grep -viE 'device_discovery|GetGpuDevices|ReadFileContents' | tail -8`
Expected: all tests pass (config, stt, llm, tts, db, router, extract, inventory).

- [ ] **Step 2: Restart the service with the new code**

Run: `ssh ngiusti@192.168.88.12 "sudo systemctl restart john-whisk && sleep 8 && systemctl is-active john-whisk"`
Expected: `active`.

- [ ] **Step 3: Live voice test (needs mic + speaker)**

With the service running, do two turns:
1. "hey jarvis" → beep → *"I bought two chicken breasts, a dozen eggs, and some spinach"* → John Whisk should confirm what it stored.
2. "hey jarvis" → beep → *"what can I make?"* → John Whisk should suggest a recipe using those items.

Then verify persistence:
Run: `ssh ngiusti@192.168.88.12 "sqlite3 ~/john-whisk/john_whisk.db 'SELECT name, quantity FROM inventory;'"`
Expected: rows for chicken breast, eggs, spinach.
(If `sqlite3` CLI is missing: `./venv/bin/python -c "from john_whisk import db; print(db.get_inventory())"` from `~/john-whisk`.)

- [ ] **Step 4: Commit any fixups + push**

```bash
cd ~/john-whisk && git add -A && git commit -m "test(inventory): full suite green" || echo "nothing to commit"
git push origin master
```

---

## Deferred (NOT in this plan — next iterations)

- "We're out of X" (remove) and "what do I have?" (list stock).
- Expiration dates, allergen/diet filters, unit normalization, per-recipe quantity math.
- Decrementing inventory after cooking.

# John Whisk — Voice Inventory (Design)

> Date: 2026-07-27
> Status: Approved design, pre-implementation
> Parent spec: `KITCHEN_ASSISTANT.md` (Phase 2). Builds on the working voice loop.

## Purpose

Phase 2, first slice: give John Whisk a pantry it tracks by voice.

- **Add with quantities:** *"I bought two chicken breasts, a dozen eggs, and some spinach"* → stored.
- **Suggest from stock:** *"What can I make?"* → recipe ideas centered on what's on hand.

Everything stays offline on the Pi and plugs into the existing `handle_turn` loop.

**Deliberately out of scope (YAGNI, later iterations):** "we're out of X" (remove),
"what do I have" (list stock), expiration dates, allergen/diet filters, unit normalization
beyond basic storage.

## Approach

Chosen: **keyword router + LLM only where needed** (Approach B). Python fast-routes the
transcript by keywords; the LLM does only the hard parts (parse quantities for *add*,
reason about recipes for *suggest*). General questions keep today's single-LLM-call path
— no added latency. Matches the project principle: keep the LLM out of the hot path for
pure intent/data operations.

Recipe suggestions are **flexible** — centered on current stock, and may name one or two
common items the user would need to add (rarely comes up empty with a small pantry).

## Modules (added to the existing `john_whisk/` package)

| File | Responsibility | Depends on |
|---|---|---|
| `db.py` | SQLite: `init_db()`, `add_items(items)`, `get_inventory()`. Owns the DB file. No LLM. | stdlib `sqlite3`, `config` |
| `router.py` | `classify(text) -> "add" \| "suggest" \| "general"`. Keyword patterns, instant, deterministic. | none |
| `inventory.py` | `add_from_text(text) -> str` (LLM-extract → `db.add_items` → confirmation) and `suggest(text) -> str` (read stock → LLM recipe). | `db`, `llm` |
| `llm.py` (extend) | `extract_items(text) -> list[dict]` (Ollama `format=json`); `suggest_from_inventory(stock, text) -> str`. Keep `ask()`. | `requests`, `config` |
| `main.py` (edit) | `handle_turn`: route transcript → add / suggest / general → speak. | `router`, `inventory`, `llm` |

Each module answers: what it does, how to call it, what it depends on — and is testable
in isolation (db against a temp SQLite; router pure; inventory against a temp db).

## Data model

SQLite file at `config.DB_PATH` = `~/john-whisk/john_whisk.db` (gitignored).

```sql
CREATE TABLE IF NOT EXISTS inventory (
    id        INTEGER PRIMARY KEY,
    name      TEXT NOT NULL,   -- normalized lowercase, e.g. "chicken breast", "eggs"
    quantity  REAL,            -- 2, 12, ...  or NULL for vague ("some")
    unit      TEXT,            -- e.g. "breasts"  or NULL
    added_at  TEXT NOT NULL    -- ISO 8601 timestamp
);
```

**Item shape** (from `extract_items`, stored by `add_items`):
`{"name": str, "quantity": float|None, "unit": str|None}`.

**Merge on add:** `add_items` upserts by normalized `name`. If the name exists, sum the
numeric quantities; if either side is `NULL` (vague), the merged quantity becomes `NULL`
("unknown amount"). Example: "two eggs" then "a dozen eggs" → 14 eggs.

## Intent routing (`router.classify`)

Case-insensitive substring/pattern match on the transcript. **Precedence: suggest → add →
general** (a question about making food wins over an incidental "bought").

- **suggest** triggers: "what can i make", "what can i cook", "what should i", "suggest",
  "recipe", "what's for dinner", "ideas for dinner", "make with".
- **add** triggers: "bought", "got", "grabbed", "picked up", "purchased", "add", "just got",
  "stock up", "i have", "we have".
- **general** = anything else → existing `llm.ask` path.

Unmatched phrasings fall through to *general* (safe: John Whisk just answers conversationally).

## LLM functions (`llm.py`)

- `extract_items(text) -> list[dict]`: Ollama call with `options.num_ctx` and Ollama's
  JSON mode (`format="json"`), prompt: *extract the grocery items and quantities the user
  said they bought; return `{"items":[{"name","quantity","unit"}]}`*. Parse + validate;
  on any failure return `[]`.
- `suggest_from_inventory(stock, text) -> str`: build a prompt injecting the current stock
  list + the flexible instruction (1–2 recipe ideas mostly using stock; may mention one or
  two common missing items; short spoken answer, no markdown). Reuses the John Whisk persona.

## Flow (`handle_turn`)

```
listener.wait() → chime → record_until_silence → stt.transcribe → text
   │
   ▼  intent = router.classify(text)
 ┌─ "add"     → reply = inventory.add_from_text(text)   # extract → store → read back
 ├─ "suggest" → reply = inventory.suggest(text)         # read stock → LLM (flexible)
 └─ "general" → reply = llm.ask(text)                   # unchanged
   │
   ▼  tts.speak(reply)   → back to wake-listening
```

**Add always confirms aloud** what it stored, e.g. *"Added two chicken breasts, a dozen
eggs, and spinach."* — essential feedback for a hands-free UI.

## Error handling (loop must never die)

| Situation | Behavior |
|---|---|
| `extract_items` returns nothing / bad JSON | Speak "I didn't catch what you bought — try again." |
| "What can I make?" with empty pantry | Speak "Your pantry's empty — tell me what you bought first." |
| DB error | Log to `john_whisk.log`, speak brief apology, continue loop |
| LLM error on suggest | Speak "Sorry, my brain hiccupped — try again." |

## Testing (all no-hardware; pytest)

- `db`: `add_items` + `get_inventory` round-trip; quantity-merge (2 + a dozen = 14; vague → NULL). Temp SQLite file.
- `router`: `classify()` over a table of sample phrases → expected intent, incl. precedence.
- `llm.extract_items`: a sample sentence → items with expected names/quantities (hits live Ollama).
- `inventory.add_from_text` / `suggest`: against a temp DB (patch `config.DB_PATH`).

## Config additions

- `DB_PATH = os.path.join(HOME, "john-whisk/john_whisk.db")`
- Extraction/suggest prompt strings (kept in `config` alongside `SYSTEM_PROMPT`).

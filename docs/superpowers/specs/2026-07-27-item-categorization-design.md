# Item Categorization — Design

Status: approved 2026-07-27. Phase 2 follow-up to the no-fabrication pantry work.

## Goal

Let pantry questions work by category, not just exact item name:
- "do we have any sauces" -> lists items tagged `sauce` (marinara, alfredo).
- "what kind of pasta do I have" -> lists items tagged `pasta` (penne, spaghetti).
- "do we have marinara" -> still matches by name.
Always DB-grounded — never invents items (extends [[2026-07-27-... no-fabrication]]).

## Decisions (resolved during brainstorming)

- **Category source:** the LLM tags each item at ADD-time (extends the existing
  extraction call). Automatic, handles any item, no keyword lists to maintain.
- **Category set:** a FIXED list of 16, so queries are reliable (everything saucy
  lands in `sauce`, not scattered across sauce/condiment/topping). Off-list ->
  `other`.
- **Existing items:** backfill the 6 already logged so the feature works now.
- **Category-query reply:** LIST the matching items (not just "yes").

## The 16 categories (`config.CATEGORIES`)

sauce, pasta, vegetable, fruit, protein, dairy, grain, spice, condiment,
beverage, baking, oil, legume, nuts, herb, other

(protein = meat/fish/eggs/tofu; grain = grain/bread/rice; spice = dried
spice/seasoning; herb = fresh herb; oil = oils & fats; other = catch-all.)

## Components

### `john_whisk/db.py` — schema + migration + category matching
- `init_db()` creates the table WITH a `category TEXT` column, and migrates an
  existing DB that predates the column:
  `PRAGMA table_info(inventory)`; if `category` absent,
  `ALTER TABLE inventory ADD COLUMN category TEXT`. Safe, no data loss; old rows
  get NULL (treated as uncategorized).
- `add_items` stores `category` (from each item dict, default None).
- `match_query(term) -> list[str]`: return stored item names whose NAME matches
  `term` (existing singular/plural tolerance) OR whose CATEGORY matches `term`.
  This is the one function that makes category queries work.
- `set_category(name, category)`: small helper for the one-time backfill.

### `john_whisk/config.py`
- `CATEGORIES` = the fixed 16 (a list, for validation + prompt).
- `EXTRACT_PROMPT` extended: also return `"category"` for each item, chosen ONLY
  from that list; use `other` if nothing fits. Keep the existing strict
  quantity rules.

### `john_whisk/llm.py`
- `extract_items` also reads `category`: validate against `config.CATEGORIES`
  (case-insensitive); anything invalid/missing -> `"other"`. Returned dict gains
  a `category` key.

### `john_whisk/inventory.py`
- `parse_queried_names` reworked to strip question SCAFFOLDING from anywhere in
  the utterance, not just leading lead-ins, so the item/category term is found
  whether mid-sentence or trailing:
  - scaffold tokens/phrases removed: "what kind of", "what sort of", "what",
    "kind", "sort", "do i have", "do we have", "have i got", "have we got",
    "got", "is there", "are there", "in stock", "in my pantry",
    "in the fridge", "in the pantry", plus the existing fillers
    (the/any/some/a/an/my/our/more/left/still).
  - "what kind of pasta do i have" -> "pasta"; "do we have any sauces" ->
    "sauces"; "have we got any olive oil" -> "olive oil".
- `check` uses `db.match_query` per term:
  - term matches items (by name or category) -> those go in `have`.
  - term matches nothing -> goes in `missing`.
  - reply: all-have -> "Yes, you have <items>."; all-missing -> "No, I don't see
    any <terms> on your list."; mixed -> "You have <items>, but no <terms>."
  - de-duplicate `have` (a specific-item + its category could both match).

### `john_whisk/main.py`
No change — category questions already route to the `check` intent (they contain
"do i have" / "do we have", or are caught by the reworked parse under check).

## Backfill (one-time, on-device)

After deploy, classify the 6 existing items via `db.set_category` (or an LLM
pass): broccoli->vegetable, chicken->protein, eggs->protein, lettuce->vegetable,
spinach->vegetable, tomatoes->vegetable. Verified by "do we have any vegetables".

## Testing (TDD)

- `llm.extract_items`: returns a valid category; an off-list/missing category
  falls back to `other` (HTTP mocked).
- `db`: migration adds the column to a pre-existing category-less DB without
  losing rows; `add_items` persists category; `match_query` matches by name and
  by category (with singular/plural on both).
- `inventory.parse_queried_names`: "what kind of pasta do I have" -> ["pasta"];
  existing "do we have any sauces" -> ["sauces"] still holds.
- `inventory.check`: category query lists the tagged items; empty category ->
  "No, I don't see any ...".
- On-device: add "marinara and penne", then "do we have any sauces" lists
  marinara, "what kind of pasta do I have" lists penne.

## Out of scope (future)

- Editing an item's category by voice.
- Multiple categories per item.
- Category-filtered recipe suggestions ("a pasta dish").

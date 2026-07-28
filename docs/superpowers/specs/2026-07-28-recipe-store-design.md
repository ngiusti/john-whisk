# Recipe Store & Importers — Design

Status: approved-in-principle 2026-07-28 (clarifying answers gathered). Adds a
stored recipe repository John Whisk cooks from, plus importers to fill it.
Revisits the original "recipe source" decision (was LLM-only) — now hybrid:
prefer a stored recipe, fall back to LLM generation.

## Goal

Give John Whisk a library of real recipes it can search and cook from, instead
of generating every recipe on the fly. Bonus: cooking from stored recipes does
not depend on the LLM, sidestepping the llama3.2:1b recipe-generation weakness.

## Decisions (from brainstorming)

- **Source:** an openly-licensed/public-domain recipe dataset (breadth) AND
  import from websites (per-URL + a guarded whole-site crawl).
- **Store miss:** prefer a stored recipe; if none matches, fall back to
  `llm.generate_recipe` (today's behavior). Nothing breaks for un-stored dishes.
- **Build scope:** everything, including the guarded whole-site importer.
- **Retrieval:** keyword/fuzzy on title + ingredients (offline, no embeddings —
  right for the 4GB Pi).

## Responsible-scraping constraints (non-negotiable, for the site importer)

- Obey `robots.txt` (stdlib `urllib.robotparser`); skip disallowed URLs.
- Rate-limit (~1 request / 2-3 s) and cap the count (`max_recipes`, default 50).
- Same-domain only; identify with a clear User-Agent.
- Only read structured recipe data the site publishes for machines
  (schema.org/Recipe). Intended for sites that permit it or that the user owns.
- Import is an admin/setup action (CLI, agent-run), never voice-triggered.

## Architecture

### 1. Recipe store — `john_whisk/recipes.py` + separate `recipes.db`
Separate SQLite file (`config.RECIPES_DB_PATH`, default `~/john-whisk/recipes.db`)
so the bulk recipe library is independent of the pantry state (`john_whisk.db`)
and can be rebuilt/shipped on its own.

Table `recipes(id, title, title_norm, ingredients TEXT, steps TEXT (JSON list),
source TEXT, tags TEXT, added_at TEXT)`.

Module API (pure, testable; `RECIPES_DB_PATH` monkeypatchable like `DB_PATH`):
- `init_db()` — create table if absent (+ future migrations).
- `add_recipe(title, ingredients, steps, source="", tags="")` — insert;
  dedupe by `title_norm` (skip/update if already present). `steps` stored as
  JSON. Returns True if added.
- `find(dish) -> dict|None` — best match for a spoken dish. Normalize the query;
  score candidates by title match (exact > substring > word-overlap) plus
  ingredient-word overlap; return `{title, ingredients, steps}` (steps as a list)
  for the best above a threshold, else None.
- `search(query, limit=5) -> list[dict]` — ranked matches (for "what recipes do
  you have for X").
- `count() -> int`.

### 2. Cooking integration — `john_whisk/cooking.py`
`start(dish)` gains a store-first lookup:
`recipe = recipes.find(dish) or llm.generate_recipe(dish)`.
Both return the same `{title, ingredients, steps}` shape, so the rest of
`start` / `CookingSession` is unchanged. A stored hit needs no LLM.

### 3. Recipe query intent — `router.py` + `inventory`/`recipes`
New `recipe_query` intent for "do you have a recipe for X" / "what recipes do you
have" / "how many recipes". Routes to a `recipes`-backed responder that reads the
store back (deterministic, no fabrication). Precedence: before `cook` is NOT
needed — these are questions, so place `recipe_query` before `suggest`/`cook`
only for the explicit "do you have a recipe" phrasing; keep "let's make X" as
`cook`. (Triggers scoped tightly to avoid shadowing cook/suggest.)

### 4. Importers — `john_whisk/recipe_import.py` (CLI + functions)
- `parse_recipe_page(url) -> dict|None` — fetch the page, extract schema.org
  Recipe structured data (JSON-LD `<script type=application/ld+json>`, incl.
  `@graph`/arrays), return `{title, ingredients, steps, source=url}`. Use the
  `recipe-scrapers` library if it installs cleanly on the Pi's py3.13 (purpose-
  built, handles many sites); otherwise a stdlib JSON-LD fallback parser.
- `import_url(url)` — parse + `recipes.add_recipe`.
- `import_dataset(path)` — load an openly-licensed dataset file (format decided
  at build time after vetting the license) into the store in bulk.
- `import_site(base_url, max_recipes=50)` — discover recipe URLs via
  `sitemap.xml` (preferred) or same-domain links, filter with `robots.txt`,
  rate-limit, cap at `max_recipes`, import each via `import_url`. Logs what it
  skipped (robots-disallowed, unparseable, cap reached) — no silent truncation.

### 5. Config — `john_whisk/config.py`
`RECIPES_DB_PATH`, `IMPORT_USER_AGENT`, `IMPORT_RATE_LIMIT_S=2.5`,
`IMPORT_MAX_RECIPES=50`.

## Data flow

Import (setup): dataset/URL/site -> `recipe_import` -> `recipes.add_recipe` ->
`recipes.db`. Cook (runtime): "let's make X" -> `cooking.start` ->
`recipes.find(X)` hit -> CookingSession from stored steps (no LLM); miss ->
`llm.generate_recipe`.

## Error handling

- Unparseable/blocked page -> `parse_recipe_page` returns None; `import_site`
  skips and logs it, continues.
- Network failure -> logged, skipped; import is resumable (dedupe by title).
- Empty store / no match -> `find` returns None -> LLM fallback (cooking) or a
  spoken "I don't have that one saved yet" (recipe_query).
- `recipes.db` absent -> `init_db` creates it.

## Testing (TDD)

- `recipes`: add + dedupe; `find` ranks exact > substring > word-overlap and
  returns None below threshold; steps round-trip through JSON; `count`/`search`.
- `cooking.start`: stored hit builds a session WITHOUT calling the LLM (assert
  `llm.generate_recipe` not called); miss falls back to it. (`recipes.find`
  monkeypatched.)
- `router`: recipe_query triggers classify correctly; "let's make X" stays cook;
  "what can I make" stays suggest.
- `recipe_import.parse_recipe_page`: parses a saved sample JSON-LD fixture into
  the right dict (no live network in unit tests); `import_site` obeys a mocked
  robots.txt (skips disallowed) and respects `max_recipes`.
- On-device: import a small openly-licensed dataset, then "let's make <a stored
  dish>" cooks from the stored recipe (verify no LLM call / instant); import one
  real recipe URL (respectful single fetch) and cook it.

## Out of scope (future)

- Semantic/embedding search (keyword/fuzzy is enough for now).
- Editing stored recipes by voice.
- Scaling the crawler beyond a bounded per-site cap.
- Nutrition/tags-based filtering (separate Phase 2 line item).

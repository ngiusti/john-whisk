# Nutritional Tracking — Design

Status: approved 2026-07-28. Add calorie/macro awareness to John Whisk: per-recipe
and per-food nutrition on demand, a daily intake log, and daily goals with
remaining — all fully offline. Built in phases.

## Decisions (from brainstorming)

- **Use case:** both per-recipe/per-food lookups AND a daily intake log, phased.
- **Data source (offline):** a **hybrid** — a curated local nutrition table for
  common foods (distilled from USDA FoodData Central, public domain) for fast,
  accurate lookups, with a **llama3.2 fallback** for foods not in the table,
  clearly flagged as an estimate.
- **Goals:** full daily goals for **calories AND macros** (protein/carbs/fat),
  each reported with a remaining amount.
- **Accuracy caveat:** numbers are approximations (curated table + unit
  conversions + LLM guesses) — for awareness, not a medical/precise tracker.

## The offline data foundation

The hard problem is turning "1 cup rice" into calories/macros. That needs three
things, all local:

1. **Per-100g nutrients** for each food (calories, protein, carbs, fat).
2. **Household-portion weights** (1 large egg = 50 g, 1 cup flour = 120 g,
   1 tbsp oil = 14 g) to convert recipe quantities to grams.
3. **Name matching** from a recipe ingredient to a table entry.

### `data/nutrition.json` (committed seed)

A curated set of a few hundred common foods, each:

```json
{
  "name": "egg",
  "aliases": ["eggs", "large egg"],
  "per_100g": {"calories": 143, "protein": 12.6, "carbs": 0.7, "fat": 9.5},
  "portions": {"large": 50, "medium": 44, "cup": 243}
}
```

This is **public domain** (USDA-derived), small, and committed to the repo — so
it always ships with the app, needs no runtime download, and is reproducible.
(Contrast `recipes.db`, which stays gitignored for copyright reasons.)

### `scripts/build_nutrition_seed.py` (one-off admin tool)

Downloads USDA FoodData Central (SR Legacy / Foundation Foods CSV bundle,
public domain), filters to a curated common-food list, pulls per-100g nutrients
and `food_portion` household weights, and writes `data/nutrition.json`. Run
once by a maintainer; not part of the runtime. Documented so the seed can be
regenerated/extended.

## Components

Module-per-feature, matching the existing codebase (inventory, cooking, etc.).

### `nutrition.py` — the engine
- `init_db()` — creates `nutrition_foods` (reference), `daily_log`, and
  `nutrition_goals` tables; loads `data/nutrition.json` into `nutrition_foods`
  on first use (idempotent).
- `parse_ingredient(line)` → `(quantity: float|None, unit: str|None, food: str)`
  — deterministic parse of a recipe ingredient line ("1 cup dried lentils" →
  (1, "cup", "lentils")). Reuses number-word handling already used for pantry
  extraction.
- `lookup(food)` → per-100g macros or None — fuzzy, plural-tolerant name match
  (same approach as `db.match_query` / `_plural_eq`).
- `to_grams(quantity, unit, food)` → grams — uses the food's `portions` table,
  falling back to common-unit defaults (tbsp = 15 g, cup = 240 g for liquids,
  etc.); returns None if it cannot convert.
- `for_food(quantity, unit, food)` → `{calories, protein, carbs, fat,
  estimated: bool}` — single-food nutrition; `estimated=True` when the LLM
  fallback was used.
- `for_recipe(recipe, servings=None)` → `{per_serving, total, unmatched: [...],
  estimated: bool}` — sums ingredients, divides by servings (recipe's own or a
  default), lists ingredients it could not resolve.
- `describe(nutr)` → a short spoken sentence ("About 620 calories a serving:
  34 grams protein, 45 carbs, 32 fat.").

### LLM fallback — `llm.estimate_nutrition(text)`
Strict-JSON prompt returning `{calories, protein, carbs, fat}` for a food or
recipe the local table can't cover. Always flagged as an estimate in the reply.
Used only on a local-lookup miss (keeps the weak 3B off the hot path when we
have real data).

### Daily log + goals (user state, in the pantry DB `john_whisk.db`)
- `daily_log(date, food, quantity, calories, protein, carbs, fat)` — one row
  per logged item; "today" is filtered by date, history retained.
- `nutrition_goals(calories, protein, carbs, fat)` — a single settable row.
- `log_food(text)` — parse one or more foods from speech, estimate, insert with
  today's date. Handles "I ate a serving of <recipe>" by resolving the recipe
  and logging its per-serving nutrition.
- `today()` → today's summed totals.
- `remaining()` → goals minus today's totals (per field).
- `set_goal(field, value)` / `answer_status()` — "1,450 of 2,000 calories,
  90 of 150 grams protein…".

## Data flow

- **Per-recipe:** "how many calories in chicken alfredo" → `recipes.find` →
  `nutrition.for_recipe` → spoken per-serving summary. Result cached on the
  recipe row (new nullable columns `cal, protein, carbs, fat` in `recipes.db`)
  so it is computed once.
- **Per-food:** "how many calories in two eggs" → parse → `for_food` → reply.
- **Daily log:** "log two eggs and toast" → `log_food` → inserted; "how am I
  doing today" → `answer_status`.
- **Goals:** "set my calorie goal to 2000" / "set my protein goal to 150 grams"
  → `set_goal`.

## Router intents

Three new keyword intents in `router.classify`, ordered before `general`:
- `nutrition_query` — "how many calories/macros in …", "how am I doing today",
  "what have I eaten".
- `nutrition_log` — "log …", "I ate …", "I had …".
- `nutrition_goal` — "set my … goal to …".

Care with precedence so these don't shadow existing intents (e.g. "I ate a
serving of X" must not hit the cooking intent). Dispatched in `main.process_utterance`.

## Phone dashboard (`web.py`)

A new **Nutrition tab**:
- Today's totals vs goals as progress bars (calories + macros).
- The day's log entries, each removable; an add field ("log a food").
- Goal settings (calories + macros).
Reuses the `nutrition` module; JSON API mirrors the existing pattern
(`GET/POST /api/nutrition/log`, `GET/POST /api/nutrition/goals`,
`GET /api/nutrition/today`).

## Phasing

- **Phase A — engine + lookups:** seed + `nutrition_foods` + `parse_ingredient`,
  `lookup`, `to_grams`, `for_food`, `for_recipe`, `describe`; LLM fallback;
  `nutrition_query` for "calories/macros in X" (recipe & food). Recipe caching.
- **Phase B — log + goals:** `daily_log`, `nutrition_goals`, `log_food`,
  `today`, `remaining`, `set_goal`, `answer_status`; `nutrition_log` and
  `nutrition_goal` intents; "I ate a serving of <recipe>".
- **Phase C — dashboard:** Nutrition tab + JSON API.

Each phase ships and is tested before the next.

## Error handling

- Ingredient the table can't match and the LLM can't estimate → excluded from
  the total and surfaced ("couldn't estimate the saffron").
- Unit with no gram conversion → skip that ingredient, note it.
- Malformed goal ("set my calorie goal to banana") → ask for a number.
- Empty/zero recipe → report that no nutrition could be computed.
- LLM fallback failure → degrade to "couldn't estimate that," never crash.

## Testing (TDD)

Deterministic throughout; LLM fallback mocked.
- `parse_ingredient`: quantities, units, number words, no-quantity cases.
- `lookup`: exact, plural, alias, miss.
- `to_grams`: portion-table hit, common-unit default, unconvertible.
- `for_recipe`: sums a fixture table correctly, per-serving division, unmatched
  list, estimated flag.
- daily log: add, today's total, multi-item, date isolation.
- goals: set, remaining math, status sentence.
- router: each intent classified; precedence vs cooking/inventory.
- dashboard: log add/remove, goals get/set, today totals.

## Out of scope (future)

- Micronutrients (vitamins/minerals), fiber/sugar/sodium breakdowns.
- Barcode scanning, weekly/historical trends and charts.
- Per-person profiles; activity/calories-burned.
- Auto-logging a recipe on cook (logging stays explicit to avoid over-counting).

# Allergen & Dietary Restriction Management — Design

Status: approved 2026-07-28. Set dietary restrictions once; they filter
suggestions and warn (with substitutions) when cooking/planning a recipe that
violates them. First of the composable-constraint filters.

## Decisions (from brainstorming)

- **Keyword rules** for detection (deterministic, offline, testable; the weak
  LLM is not trusted with allergen safety). Always include a "double-check the
  labels" caution — it's a helpful filter, not a medical guarantee.
- **Warn-and-proceed**, NO hard "cook anyway?" gate.
- **Suggest restriction-compliant substitutes** for violating ingredients
  ("soy cream instead of heavy cream"), also keyword-mapped.
- Applies to: suggestions (filtered), and cook + plan (warn + substitutions).

## Components

### `john_whisk/restrictions.py`

**Store** — `restrictions` table in the pantry DB (`config.DB_PATH`):
`id, restriction, added_at`. `add(names)`, `remove(names)`, `active()` (list),
`clear()`. Restriction names normalized to canonical keys.

**Canonical restrictions + rule map** — `RULES: {restriction: [banned keywords]}`:
- `nuts`: almond, walnut, pecan, cashew, peanut, pistachio, hazelnut, pine nut,
  macadamia, nut
- `gluten`: wheat, flour, bread, pasta, barley, rye, couscous, breadcrumb,
  cracker, noodle, gluten
- `dairy`: milk, cheese, butter, cream, yogurt, parmesan, mozzarella, dairy
- `eggs`: egg
- `shellfish`: shrimp, prawn, crab, lobster, oyster, clam, mussel, scallop,
  shellfish
- `fish`: fish, salmon, tuna, cod, anchovy, tilapia, halibut, sardine
- `soy`: soy, tofu, edamame, miso
- `pork`: pork, bacon, ham, sausage, prosciutto
- `vegetarian`: (all meat/seafood keywords: chicken, beef, pork, lamb, turkey,
  bacon, ham, sausage, prosciutto, meat + all `fish`/`shellfish` keywords)
- `vegan`: vegetarian keywords + dairy keywords + egg + honey

**Name normalization** — `_canonical(text)` maps spoken phrasings to keys:
"allergic to nuts"/"nut allergy"/"no nuts" -> `nuts`; "gluten free"/"no gluten"
-> `gluten`; "dairy free" -> `dairy`; "vegetarian" -> `vegetarian`; "vegan" ->
`vegan`; etc. Returns None if unrecognized.

**Substitution map** — `SUBS: {restriction: {banned keyword: compliant sub}}`:
- dairy: cream->soy cream, milk->oat milk, butter->olive oil,
  cheese->dairy-free cheese, parmesan->nutritional yeast, yogurt->coconut yogurt
- gluten: flour->gluten-free flour, pasta->gluten-free pasta,
  bread->gluten-free bread, breadcrumb->gluten-free breadcrumbs, noodle->rice noodles
- vegetarian/vegan: chicken->tofu, beef->lentils, pork->mushrooms, bacon->tempeh,
  fish->tofu, shrimp->hearts of palm, sausage->veggie sausage, meat->beans
- eggs: egg->flax egg
A chosen substitute is skipped if it would itself violate ANOTHER active
restriction (e.g. don't suggest almond milk when nut-allergic); fall back to the
next option or omit the "instead of" clause.

**Detection + messaging**
- `check(ingredients_str) -> list[dict]`: for each ACTIVE restriction, find
  recipe ingredients (split on ", ") containing a banned keyword (whole-word,
  singular/plural tolerant so "butter" != "nut"); return
  `{restriction, ingredient, keyword, sub}` (sub = compliant substitute or None).
- `warning(recipe) -> str`: build the spoken heads-up from `check`, e.g.
  "Heads up — Chicken Alfredo has dairy. Try soy cream instead of the cream and
  nutritional yeast instead of the parmesan. For a real allergy, double-check
  the labels." Returns "" when nothing is violated.
- `answer_list() -> str`: "Your restrictions are X and Y." / "You haven't set any
  restrictions."
- `set_from_text(text)` / `remove_from_text(text)`: parse a restriction from
  "I'm allergic to X" / "I'm gluten free" / "remove the X restriction" /
  "I can eat X again".

### Integration
- `inventory.suggest` — prepend active restrictions to the `suggest` prompt
  ("I am vegetarian and avoid dairy; do not suggest recipes with those.").
- `cooking.start` — after `recipes.resolve`, prepend `restrictions.warning(recipe)`
  to the opening (warn-and-proceed; session still starts).
- `grocery.plan_meal` — prepend `restrictions.warning(recipe)` to the plan reply.
- `router` — new `dietary` intent for set/list/remove/clear restrictions:
  triggers "allergic to", "i'm gluten free"/"gluten free", "i'm vegetarian"/
  "vegetarian", "vegan", "dairy free", "my restrictions", "dietary",
  "i can eat", "remove the ... restriction". Placed before add/remove/suggest so
  "I'm allergic to nuts" isn't a pantry add and "vegetarian" isn't a suggest.
- `main` — `dietary` -> a small dispatcher (list / set / remove / clear).

## Data flow

Set: "I'm allergic to nuts" -> `restrictions.set_from_text` -> canonical `nuts`
-> store. Cook/plan: resolve recipe -> `restrictions.warning(recipe)` prepended.
Suggest: active restrictions injected into the LLM prompt.

## Error handling / edge cases

- Unrecognized restriction phrase -> "I'm not sure which restriction you mean."
- No active restrictions -> `warning` returns "" (no-op everywhere).
- Substitute would violate another active restriction -> pick next / omit it.
- Whole-word matching so "butter"/"peanut butter" don't falsely trip unrelated
  restrictions; "peanut" still trips `nuts`.

## Testing (TDD)

- store: add (normalize + dedupe), remove, active, clear.
- `_canonical`: phrasings -> keys; unknown -> None.
- `check`: dairy recipe flags cream/parmesan with subs; vegetarian flags chicken
  -> tofu; no false positives (whole-word); inactive restrictions ignored;
  substitute avoids other active restrictions (nut+dairy -> not almond milk).
- `warning`: builds the heads-up incl. subs + the label caution; "" when clean.
- `inventory.suggest`: prompt carries the restrictions.
- `cooking.start` / `grocery.plan_meal`: warning prepended when violating, absent
  when clean (restrictions monkeypatched).
- router: dietary intent vs add/suggest precedence.
- On-device: set "dairy" + "vegetarian", then "let's make chicken alfredo" warns
  with substitutions; "what are my restrictions" reads them; suggestions respect
  them.

## Out of scope

- Composing with time/budget/equipment filters (future composable-constraints).
- Learning tolerance over time; per-guest profiles beyond add/remove.
- Guaranteeing safety — keyword rules can miss unusual ingredients (hence the
  caution).

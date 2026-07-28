# Grocery List & Meal Planning — Design

Status: approved 2026-07-28. Adds a grocery list and a "plan a meal" flow that
adds missing ingredients to it.

## Goal

"I would like to make X" → John Whisk finds the recipe, checks it against the
pantry, and adds the ingredients you're missing to a grocery list, saying
"Adding missing ingredients: X, Y, and Z." Planning only — it does not start
cooking ("let's make X" still cooks).

## Decisions (from brainstorming)

- **Plan-only** for "I would like to make X" — separate from cooking.
- **Auto-add** the missing ingredients to the list.
- **Skip basic staples** (salt, pepper, water, oil) — never added.
- **Reply wording:** "Adding missing ingredients: X, Y, and Z."

## Components

### `john_whisk/grocery.py` — the grocery list store + commands
`grocery` table in the pantry DB (`config.DB_PATH`): `id, item, added_at`.
- `add(items)` — insert, dedupe by normalized item; accepts a list or string.
- `items()` — list of item strings.
- `remove(names)` — delete matching (substring/normalized).
- `clear()` — empty the list.
- `answer_list()` — spoken read-back ("Your grocery list has ..." / "empty").
- `add_from_text(text)` / `remove_from_text(text)` — parse an item from a spoken
  "add X to my grocery list" / "remove X from my grocery list".

### Missing-ingredient detection — `grocery._missing(ingredients_str, pantry)`
Split the recipe's ingredient string on ", " into individual ingredients. An
ingredient is COVERED if it is a staple (salt/pepper/water/oil) OR a pantry item
name matches a whole word in it (singular/plural tolerant — "chicken" covers
"2 chicken breasts", "egg" covers "2 eggs"). Return the missing ingredient
strings (as written, e.g. "1 cup heavy cream").

### Recipe resolution — `recipes.resolve(dish)`
Extract the shared "stored-recipe-else-LLM" lookup out of `cooking.start` into
`recipes.resolve(dish) -> recipe dict | None` (= `find(dish) or
llm.generate_recipe(dish)`). `cooking.start` calls it; the planner reuses it.
(recipes.py gains an `llm` import; no cycle — llm doesn't import recipes.)

### Planner — `grocery.plan_meal(dish)`
1. `recipe = recipes.resolve(dish)`; if None -> "I don't have a recipe for X."
2. `missing = _missing(recipe["ingredients"], db.get_inventory())`.
3. If none missing -> "You've got everything for {title}!"
4. `add(missing)`; return "Adding missing ingredients: " + join + "."

### Router — `john_whisk/router.py`
- `plan` intent — "i would like to make", "i'd like to make", "i want to make",
  "planning to make", "plan to make", "what do i need to make",
  "what do i need for", "add ingredients for", "shop for".
- `grocery` intent — "grocery list", "shopping list", "what do i need to buy",
  "need to buy". (Placed BEFORE add/remove so "add X to my grocery list" /
  "remove X from my grocery list" don't fall into pantry add/remove.)
- Precedence: volume -> cook -> recipe_query -> plan -> grocery -> suggest ->
  list -> check -> remove -> add -> general. (cook before plan so "let's make X"
  still cooks; plan phrasings don't overlap the router's cook triggers.)

### `john_whisk/main.py`
`process_utterance`: `plan` -> `grocery.plan_meal(cooking.dish_from_text(text))`
(dish extraction reuses/extends the cook lead-in stripper for "would like to
make" etc.); `grocery` -> a small dispatcher (list / add / remove / clear based
on the phrase).

## Spoken flow

- "I would like to make chicken alfredo" (pantry has chicken, not cream/parmesan)
  -> "Adding missing ingredients: 1 cup heavy cream, and half cup parmesan."
- "I would like to make scrambled eggs" (have eggs, butter) -> "You've got
  everything for Scrambled Eggs!"
- "What's on my grocery list?" -> reads it back.
- "Add milk to my grocery list" -> "Added milk to your grocery list."
- "Clear my grocery list" -> "Okay, cleared your grocery list."

## Error handling

- No recipe for the dish -> "I don't have a recipe for X." (nothing added)
- Empty grocery list read -> "Your grocery list is empty."
- Staples-only missing -> treated as have-everything.

## Testing (TDD)

- grocery store: add/dedupe, items, remove, clear; add/remove_from_text parsing.
- `_missing`: staples excluded; plural/whole-word pantry matching; returns the
  missing strings; have-everything -> [].
- `recipes.resolve`: stored hit returns it without calling LLM; miss falls back.
- `cooking.start` still works via resolve (no regression).
- `plan_meal`: missing -> adds + "Adding missing ingredients:"; none -> "got
  everything"; no recipe -> apology. (recipes.resolve / db / grocery isolated.)
- router: plan vs cook vs grocery precedence, incl. "add X to my grocery list"
  -> grocery (not pantry add), "let's make X" -> cook.
- On-device: "I would like to make <a stored dish>" against the real pantry adds
  the right missing items; grocery list read/add/clear work.

## Out of scope

- Removing items from the list automatically when you buy them / log them to the
  pantry (could be a nice future tie-in).
- Aisle-organized or store-specific lists.

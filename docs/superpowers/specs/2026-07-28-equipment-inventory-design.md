# Equipment / Utensil Inventory — Design

Status: approved 2026-07-28. Declare owned appliances once; recipes that need a
tool you don't have warn (cook/plan), and suggestions favor makeable recipes.
Mirrors the dietary feature (store + keyword detection + warn-and-proceed).

## Decisions (from brainstorming)

- **Keyword detection from recipe steps** (the library doesn't store equipment),
  same approach as dietary. Helpful hint, not exact — a caution applies.
- **Warn-and-proceed** on cook/plan; equipment injected into the suggest prompt.
- Track only **notable appliances**; assume basics (stovetop, pan, pot, knife,
  bowl, whisk) are always on hand.

## Components

### `john_whisk/equipment.py`
`equipment` table in the pantry DB (`config.DB_PATH`): `id, item, added_at`.

**Notable equipment + step keywords** — `RULES: {equipment: [step keywords]}`,
chosen to minimize false positives:
- `blender`: blend, blender, puree, purée, smoothie
- `food processor`: food processor
- `stand mixer`: stand mixer, electric mixer
- `slow cooker`: slow cooker, crockpot, crock pot
- `air fryer`: air fry, air fryer, air-fry
- `grill`: on the grill, grill the, barbecue, bbq
- `oven`: in the oven, bake, baked, roast, roasted, broil
- `microwave`: microwave
- `pressure cooker`: pressure cook, pressure cooker, instant pot
- `waffle iron`: waffle iron, waffle maker

**Aliases -> canonical** (`_canonical`): "crockpot"/"crock pot" -> slow cooker;
"instant pot"/"instapot" -> pressure cooker; "mixer" -> stand mixer;
"airfryer" -> air fryer; "waffle maker" -> waffle iron; otherwise the notable
name if it appears. Returns None if no notable equipment recognized.

**Store**: `add(names)`, `remove(names)`, `owned()`, `clear()`.

**Detection + messaging**
- `required(recipe) -> set`: scan the recipe's steps (joined) for each
  equipment's keywords (whole-word / phrase match); return the notable equipment
  implied.
- `missing(recipe) -> list`: `required` minus `owned`.
- `warning(recipe) -> str`: "Heads up — {title} needs a blender and an air fryer,
  which you haven't listed in your equipment." (articles a/an), or "" if none
  missing.
- `prompt_clause()`: "I have this kitchen equipment: {owned}. Prefer recipes I
  can make with it." ("" if none owned).
- `answer_list()`: spoken owned list / "You haven't listed any equipment."
- `set_from_text(text)` / `remove_from_text(text)`: pull ALL notable equipment
  mentioned ("I have a slow cooker and an air fryer" -> both).
- `handle(text)`: clear / remove / list / add dispatch (like restrictions.handle).

### Integration
- `cooking.start` — prepend `equipment.warning(recipe)` to the opening, after the
  dietary warning (both are warn-and-proceed; the session still starts).
- `grocery.plan_meal` — prepend `equipment.warning(recipe)` too.
- `inventory.suggest` — append `equipment.prompt_clause()` to the request
  (alongside dietary + ratings clauses).
- `router` — `equipment` intent. Triggers: specific appliance names (blender,
  food processor, slow cooker, crockpot, air fryer, pressure cooker, instant pot,
  waffle iron, stand mixer), plus "equipment", "appliance", "what equipment",
  "my equipment", "i have a", "i have an", "i've got a", "i don't have a".
  Placed after cook/plan/rate and before add (so "I've got a blender" isn't a
  pantry add). Bare common words (oven/grill/microwave/mixer) are NOT router
  triggers (too ambiguous) — but ARE detected in recipe steps.
- `main` — `equipment` -> `equipment.handle(text)`.

## Spoken flow

- "I have a blender and a slow cooker." -> adds both -> "Got it — I've noted your
  blender and slow cooker."
- "What equipment do I have?" -> "You have a blender and a slow cooker."
- (cook) "let's make a smoothie" with no blender owned -> "Heads up — Smoothie
  needs a blender, which you haven't listed in your equipment. Okay, making
  Smoothie..." (still proceeds)
- "what can I make" -> the suggest prompt lists your equipment.

## Error handling

- Unrecognized equipment phrase -> "I'm not sure which equipment you mean."
- No owned equipment -> `warning` still fires for missing; `prompt_clause` = "".
- Keyword over/under-detection -> accepted (hint, not exact); no hard blocks.

## Testing (TDD)

- store: add (canonical + dedupe), remove, owned, clear.
- `_canonical`: aliases -> keys; unknown -> None.
- `required`: "blend until smooth" -> blender; "bake for 20 minutes" -> oven; no
  false positive from a plain pan/stovetop step.
- `missing` / `warning`: needs-a-blender when not owned; "" when owned or none.
- `prompt_clause`: lists owned; "" when none.
- `set_from_text`: multiple appliances in one utterance.
- integration: cooking.start / plan_meal prepend warning; suggest carries the
  equipment clause.
- router: equipment intent vs cook/add precedence.
- On-device: declare a blender, "let's make" a blended recipe warns when a
  needed tool is absent; equipment reaches the suggest prompt.

## Out of scope

- Exact per-recipe equipment metadata; utensil-level tracking; composing with
  time/budget filters (future composable constraints).

# Flavor Customization — Design

Status: approved 2026-07-28. Live mid-recipe flavor tips + a saved flavor
preference that biases suggestions. The last Phase 2 high-priority item.

## Decisions (from brainstorming)

- **Both**: (A) live, mid-recipe adjustment advice ("tone down the spice"); and
  (B) a saved flavor preference ("we like it mild") that persists and nudges
  suggestions ("learns tolerance over time").
- Part A advice is LLM-generated (like substitution) — flavor advice tolerates
  imperfection, and it's inherently generative.

## Components

### `john_whisk/flavor.py`
`flavor_prefs` table in the pantry DB (`config.DB_PATH`): `id, note, added_at`.

- **Store**: `add(notes)`, `prefs()`, `remove(notes)`, `clear()`.
- `is_adjust(text) -> bool` — detects an in-recipe flavor-adjustment request via
  keywords: tone down/dial back, spicier/hotter/milder/bolder, too salty/spicy/
  bland/sweet, more/less garlic/salt/heat/flavor, spice it up, kick it up, etc.
  (Deliberately not "how hot should the pan be" — that stays a question.)
- `tip(title, step, request) -> str` — LLM advice via `llm.flavor_advice`,
  grounded in the current recipe + step + saved prefs; fallback on empty.
- `prompt_clause()` — "We like our food mild and bold." for the suggest prompt
  ("" if no prefs).
- `set_from_text(text)` — parse a preference from "we like it mild" / "we prefer
  bold flavors" / "we don't like it too spicy" (negation -> "not too <x>"); add.
- `answer_prefs()` / `handle(text)` — read/clear/set dispatch.

### `john_whisk/llm.py`
- `flavor_advice(title, step, request, prefs="") -> str` — mirrors
  `suggest_substitution`: a grounded prompt ("cooking {title}, on step {step};
  {request}; give one or two quick practical flavor tips; we like our food
  {prefs}"), returns "" on failure.

### Integration
- `cooking.Kitchen.navigate` — after the substitution check, if
  `flavor.is_adjust(text)`: `return flavor.tip(current.title, current.current(),
  text)` (stays in the recipe). `cooking` imports `flavor`.
- `inventory.suggest` — append `flavor.prompt_clause()` to the request (alongside
  dietary/ratings/equipment).
- `router` — `flavor` intent for PREFERENCES (set/read/clear): "we like it",
  "we prefer", "we like our food", "flavor preference", "spice level", "keep it
  mild", "keep it spicy", "we like bold", "we like mild", "we don't like it too",
  "our spice". Placed before rate (distinct from a recipe rating). The in-recipe
  adjustment (Part A) is caught inside navigate, so it needs no router intent.
- `main` — `flavor` -> `flavor.handle(text)`.

## Spoken flow

- (cooking) "Tone down the spice." -> "To dial back the heat, stir in a spoon of
  yogurt or a squeeze of lime and go easy on the chili." (stays on step)
- (cooking) "Make it bolder." -> "Add an extra clove of garlic and a pinch more
  salt, and finish with fresh herbs."
- "We like our food mild." -> "Got it — I'll keep your mild preference in mind."
- "What are our flavor preferences?" -> "You like your food mild."
- "what can I make" -> the suggest prompt carries the flavor preference.

## Error handling

- `llm.flavor_advice` empty (Ollama down) -> "Sorry, I couldn't think of a flavor
  tip right now."
- Unrecognized preference phrase -> "I'm not sure what flavor you mean."
- No prefs -> `prompt_clause` = "".

## Testing (TDD)

- pref store: add/dedupe, prefs, remove, clear.
- `is_adjust`: "tone down the spice"/"make it bolder"/"too salty" -> True;
  "next"/"how hot should the pan be" -> False.
- `llm.flavor_advice`: prompt carries title, step, request, prefs (HTTP mocked).
- `flavor.tip`: passes prefs; fallback on empty.
- `set_from_text`: "we like it mild" -> "mild"; "we don't like it too spicy" ->
  a not-too-spicy note.
- `prompt_clause`: contains prefs; "" when none.
- `Kitchen.navigate`: a flavor adjustment returns a tip and keeps the session;
  a normal question still hits ask_in_recipe.
- `inventory.suggest`: flavor clause reaches the prompt.
- router: flavor (preference) vs rate/suggest precedence.
- On-device: cook a real recipe, "tone down the spice" gives grounded advice and
  stays on the step; set "mild" and confirm it reaches the suggest prompt.

## Out of scope

- Auto-editing recipe quantities; numeric spice-level modeling; per-dish flavor
  memory. It's advice + a soft preference.

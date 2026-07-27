# Interactive Step-by-Step Recipe Guidance — Design

Status: approved 2026-07-27. Phase 2, first feature.

## Goal

John Whisk should walk the cook through a recipe one step at a time: read a
step, wait for a spoken command, advance/repeat/go back on request, and answer
ad-hoc questions without losing its place. Fully offline; recipe content is
generated on demand by the local LLM.

## Decisions (resolved during brainstorming)

- **Recipe source:** LLM-generated on the fly (llama3.2:3b), parsed into steps.
  No stored recipe library in this build.
- **Cooking-mode input:** wake word before each command for now
  ("hey jarvis, next"). Hands-free continuous-listen is a deliberate follow-up,
  NOT in this build.
- **Opening:** on start, read the ingredients list and wait for "next" before
  reading step 1 (lets the cook gather ingredients first).
- **Unrecognized utterance while cooking:** falls through to a context-aware LLM
  answer ("you're on step N of X; the user asked Y") and STAYS in the recipe.

## Architecture

### New module: `john_whisk/cooking.py`
Pure, fully unit-testable. No audio; no direct HTTP. Holds:

- `CookingSession` — carries `title: str`, `ingredients: str`, `steps: list[str]`,
  and `i: int` (index into `steps`; `-1` = "not started, ingredients read").
  Methods mutate/report position only:
  - `current() -> str` — the current step text.
  - `advance()` / `back()` / `restart()` — move the index within bounds.
  - `at_end` / `started` — position predicates.
- `classify_nav(text) -> str` — deterministic keyword match returning one of:
  `next`, `repeat`, `back`, `restart`, `ingredients`, `where`, `stop`, `unknown`.
  - `next`: "next", "done", "continue", "go on", "ok next", "next step".
  - `repeat`: "repeat", "again", "say that again", "what was that".
  - `back`: "back", "previous", "go back", "last step".
  - `restart`: "start over", "restart", "from the top", "beginning".
  - `ingredients`: "ingredients", "what do i need", "what are the ingredients".
  - `where`: "where am i", "what step", "which step".
  - `stop`: "stop", "quit", "exit", "cancel", "never mind", "i'm done",
    "all done", "done cooking".
  - anything else → `unknown`.
  - Note ambiguity resolution: bare "done"/"next" = advance; "i'm done" /
    "all done" / "done cooking" / "stop" = exit the recipe.
- `dish_from_text(text) -> str` — strip cook lead-ins ("let's make", "how do i
  make", "walk me through", "start the recipe for", "the", ...) to get the dish
  name. Same lead-in-stripping approach as `inventory.parse_removed_names`.
- `start(dish) -> (session|None, reply)` — calls `llm.generate_recipe(dish)`;
  on success returns a fresh session (index `-1`) plus the opening line; on
  failure returns `(None, <graceful message>)`.
- `navigate(session, text) -> (reply, session|None)` — the per-turn controller:
  classify the nav command, mutate the session, return the spoken reply and the
  updated session (`None` when the recipe ends). `unknown` → call
  `llm.ask_in_recipe(session, text)` and stay active.

### `john_whisk/llm.py`
New `generate_recipe(dish) -> dict|None` mirroring the existing Ollama calls
(same URL/model/timeout, larger `num_predict` since recipes are longer). Strict
format prompt (new `config.RECIPE_PROMPT`):

```
INGREDIENTS: eggs, butter, salt
STEPS:
1. Crack three eggs into a bowl and whisk.
2. Melt butter in a pan over medium heat.
...
```

Parser: capture the `INGREDIENTS:` line, then the numbered lines under `STEPS:`.
Returns `{"title": dish, "ingredients": str, "steps": [str]}`. If fewer than two
steps parse out (garbage / model didn't follow format), return `None`.

New `ask_in_recipe(session, text) -> str` — a thin `ask()` wrapper that prepends
recipe context to the user's question so mid-recipe questions get relevant
answers without leaving cooking mode.

### `john_whisk/router.py`
New `cook` intent. Triggers (`COOK_TRIGGERS`): "let's make", "lets make",
"let's cook", "walk me through", "guide me through", "how do i make",
"how do you make", "start the recipe", "start cooking". Precedence:
`volume -> cook -> suggest -> list -> remove -> add -> general`. Chosen so
"let's make the omelette" starts cooking while "what can I make for dinner"
stays `suggest` (the cook triggers share no substring with the suggest ones).

### `john_whisk/main.py`
`handle_turn` becomes session-aware and returns the (possibly updated / `None`)
session; `main()` threads it through the loop:

```
session = None
while True:
    session = handle_turn(listener, session)

# inside handle_turn, after transcription:
if session is not None:
    reply, session = cooking.navigate(session, text)
else:
    intent = router.classify(text)
    if intent == "cook":
        session, reply = cooking.start(cooking.dish_from_text(text))
    elif intent == "volume": ...
    # (existing add / suggest / list / remove / general branches unchanged)
return session
```

No audio-layer changes. Each command still requires the wake word (per the
input decision above).

## Spoken flow

- Start: "Okay, making an omelette. Here's what you'll need: eggs, butter, and
  salt. Say 'next' when you're ready." (session index = -1)
- "next" from -1 → "Step 1 of 6. Crack three eggs into a bowl and whisk."
- "next" → "Step 2 of 6. ..."
- "repeat" → re-reads the current step.
- "back" at step 1 → "You're on the first step." (no move)
- "ingredients" → re-reads the ingredients line, position unchanged.
- "where am I" → "You're on step 2 of 6."
- "next" past the last step → "That's the last step. Enjoy your omelette!" →
  session ends (`None`).
- "stop" / "I'm done" any time → "Okay, stopping the recipe." → session ends.
- Unrecognized ("how hot should the pan be?") → context-aware LLM answer, stays
  in the recipe.

## Error handling

- `generate_recipe` returns `None` (unparseable / too few steps / Ollama down or
  timeout — existing empty-string path) → "Sorry, I couldn't put a recipe
  together for that. Try another dish." No session starts.
- `back`/`advance` clamp to bounds; `navigate` on a finished session is not
  reachable because the session is set to `None` when it ends.

## Testing (TDD)

Deterministic unit tests, `llm.generate_recipe`/`ask` monkeypatched:

- `classify_nav` — one test per command family plus `unknown`.
- `CookingSession` — advance through to end, back clamps at start, restart,
  repeat, `where` reporting, ingredients re-read.
- `llm.generate_recipe` parser — well-formed response parses to title/
  ingredients/steps; malformed / short response → `None` (HTTP call mocked).
- `dish_from_text` — single and lead-in-stripped dish names.
- `router.classify` — "let's make X" → `cook`; guards that "what can I make"
  stays `suggest` and "I bought X" stays `add`.
- `cooking.start` / `navigate` flows — start (with a canned recipe), step
  through to the end, stop mid-way, unknown → LLM fallthrough stays active.

## Out of scope (future)

- Hands-free continuous listening while cooking (the agreed fast follow).
- Pantry-aware substitution ("I don't have pine nuts" → swap) — separate Phase 2
  line item.
- Persisting an in-progress recipe across a service restart (in-memory is fine).
- Injecting current pantry into recipe generation (that belongs to `suggest`).

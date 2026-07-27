# Recipe Queue — Design

Status: approved 2026-07-27. Phase 2 refinement to step-by-step recipe guidance
([[2026-07-27-recipe-step-guidance-design]]).

## Goal

Cook one recipe at a time without interleaving. Multiple recipes can be lined
up; John Whisk works through the current one fully, then hands off to the next.
The cook can ask what's queued.

## Decisions (resolved during brainstorming)

- **Enqueue, don't interrupt:** starting a recipe while one is active appends it
  to a queue; the current recipe keeps focus.
- **Hand-off:** when a recipe ends, announce the next and WAIT for "next" before
  reading its first step (mirrors how a single recipe waits before step 1).
- **"stop" / "I'm done":** ends the CURRENT recipe and advances to the next
  queued one. "cancel everything" / "stop all" clears current + queue.
- **Summary query:** "what recipes am I making right now" lists current + queued,
  works whether or not a recipe is active.

## Architecture

Keep `CookingSession` and the module-level `start(dish)` /
`navigate(session, text)` EXACTLY as they are (all step logic + its tests
untouched). Add a `Kitchen` orchestrator that owns the queue and calls them.

### `john_whisk/cooking.py`

`class Kitchen`:
- `current`: the active `CookingSession`, or None.
- `queue`: list of dish-name strings not yet started.
- `active` (property): `current is not None`.
- `begin(dish) -> reply`: if not active, `start(dish)` and set `current`
  (reply = its opening); if active, append `dish` to `queue`
  ("Okay, I'll make {dish} after the {current.title}.").
- `navigate(text) -> reply`: one in-recipe turn. Precedence:
  1. `_is_cancel_all(text)` -> `cancel_all()`.
  2. `_is_cook_request(text)` -> `begin(dish_from_text(text))` (enqueues, since
     active).
  3. else call module `navigate(current, text)`:
     - if it returns `session is not None` -> update `current`, return reply.
     - if it returns `session is None` (recipe ended: stop or last step) ->
       `_advance_queue(reply)`.
  (A "what am I making" query is intercepted earlier in process_utterance, so it
  works whether active or not — see main.)
- `_advance_queue(closing) -> reply`: pop dish names until one generates a
  recipe; set it as `current` (at index -1, not started) and return
  `closing + " " + next_up(session)`. If a dish fails to generate, note it and
  try the next. If the queue empties, set `current = None` and return `closing`.
- `cancel_all() -> reply`: clear `current` and `queue`;
  "Okay, cleared all the recipes."
- `summary() -> reply`: not active -> "You're not making anything right now.";
  active -> "You're making {current.title} right now" + (", with {queue joined}
  up next" if queue) + ".".

Module helpers:
- `next_up(session) -> str`: "Next up is {title}." + (" You'll need:
  {ingredients}." if any) + " Say next when you're ready."
- `is_recipes_query(text) -> bool`: matches "what am i making", "what am i
  cooking", "what recipes", "which recipes", "what are we making/cooking".
- `_is_cancel_all(text) -> bool`: contains ("everything" or "all") AND one of
  (stop, cancel, quit, forget, done). Checked before plain "stop" so the words
  don't collide.
- `_is_cook_request(text) -> bool`: contains any `router.COOK_TRIGGERS` phrase
  (reuse the router list; avoids a second copy).

Module-level `navigate(session, text)`: one wording tweak — the "stop" reply
names the recipe ("Okay, stopping the {title}.") so the hand-off reads cleanly.
(Existing test asserts only that "stop" appears — still holds.)

### `john_whisk/main.py`
- Replace the threaded `session` with `kitchen = cooking.Kitchen()`.
- Everywhere `session is not None` -> `kitchen.active`; `_listen(...)` keys on
  `kitchen.active`; `hands_free = kitchen.active and config.HANDS_FREE_COOKING`.
- `process_utterance(text, kitchen) -> reply` (mutates kitchen):
  1. `if cooking.is_recipes_query(text): return kitchen.summary()`.
  2. `if kitchen.active: return kitchen.navigate(text)`.
  3. else `router.classify`; `cook` -> `kitchen.begin(dish_from_text(text))`;
     other intents unchanged (volume/add/suggest/list/check/remove/general).
- Hands-free unknown-guard also lets a cook request / recipes query / cancel-all
  through (not just nav commands), so queue actions aren't dropped in hands-free
  mode. (Minor; hands-free is off by default.)

## Error handling

- Next recipe fails to generate -> `_advance_queue` skips it with a spoken note
  and tries the following one; empty queue -> clean end.
- Everything stays in-memory in the `Kitchen`; a service restart drops the queue
  (accepted — out of scope to persist).

## Testing (TDD)

Kitchen unit tests with `llm.generate_recipe` monkeypatched:
- `begin` starts when idle; `begin` while active enqueues (current unchanged,
  queue grows, reply mentions "after").
- Hand-off: finish the last step with a queued recipe -> announces next, waits
  (current is the next session at index -1); same via "stop".
- "stop" with empty queue -> ends (kitchen inactive).
- `cancel_all` clears both; `_is_cancel_all` distinguishes "cancel everything"
  from plain "stop".
- `summary` in 0 / 1 / 2-queued states.
- `is_recipes_query` true/false; enqueue-while-cooking via `navigate`.
- Generation failure for a queued dish is skipped with a note.
- `process_utterance` routes summary anytime, cook when idle, delegates to
  kitchen when active.
- Existing `test_cooking.py` (CookingSession, start, module navigate) stays green.
- On-device: queue two real recipes, step through the first, confirm the
  announce-and-wait hand-off into the second; ask "what am I making".

## Out of scope (future)

- Reordering the queue or "skip to <dish>" without finishing the current one.
- Persisting the queue across a restart.
- A cap on queue length.

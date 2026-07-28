# In-Recipe Ingredient Substitution — Design

Status: designed autonomously 2026-07-27 (overnight, Nicholas asleep). Decisions
were made with sensible defaults; flagged below for morning review. Phase 2
feature repeatedly deferred as "the next thing" out of recipe guidance.

## Goal

While cooking, the cook can ask for a substitute for an ingredient they lack —
"I don't have pine nuts", "what can I use instead of butter", "I'm out of eggs",
"substitute for buttermilk" — and John Whisk suggests ONE swap, preferring what's
actually in the pantry, and stays in the recipe.

## Design decisions (my calls — review these)

- **In-recipe only.** Substitution is handled inside a live recipe
  (`Kitchen.navigate`). Outside a recipe such a question still falls to the
  grounded general handler. (Keeps scope tight; mid-cook is the real use case.)
- **Pantry-grounded via the LLM.** The substitute comes from the LLM, grounded
  with the current recipe title, the current step, AND the logged pantry, so it
  prefers something the cook already has. Consistent with the no-fabrication
  work: it won't claim the cook owns something they don't, and if it suggests a
  common substitute not in the pantry it says so.
- **Deterministic trigger + ingredient parse.** Detecting a substitution request
  and extracting the ingredient is keyword-based (no LLM in that hot path),
  mirroring `parse_removed_names` / `dish_from_text`.
- **Stays in the recipe.** Answering a substitution never changes the session.
- **Enhances the existing unknown-fallthrough.** Today an unrecognized in-recipe
  utterance goes to `llm.ask_in_recipe` (step context, no pantry). Substitution
  is detected BEFORE that and routed to a pantry-grounded helper — a strictly
  better answer for "what do I use instead of X".

## Components

### `john_whisk/cooking.py`
- `_SUBSTITUTION_LEADINS` — normalized phrases that precede the missing
  ingredient: "what can i use instead of", "what can i use in place of",
  "what can i substitute for", "instead of", "in place of", "substitute for",
  "substitution for", "a substitute for", "replacement for", "replace the",
  "sub for", "swap for", "swap out the", "i don t have any", "i don t have",
  "don t have any", "don t have", "dont have", "do not have", "i m out of",
  "im out of", "i am out of", "we re out of", "out of", "ran out of",
  "no more", "i have no".
- `_is_substitution(text)` — True if any lead-in appears (normalized text).
- `parse_substitution_ingredient(text)` — strip the longest-ending lead-in
  (same best_end approach as `dish_from_text`), drop fillers
  (the/a/an/any/some/my/of/more/left), return the ingredient (may be multiword).
- `Kitchen.navigate` precedence becomes:
  cancel-all -> cook-request(enqueue) -> **substitution** -> nav -> unknown-LLM.
  On substitution with a parsed ingredient:
  `return inventory.substitute(self.current.title, self.current.current(), ingredient)`.
  (Empty ingredient -> fall through to normal handling.)
- `cooking` gains `from john_whisk import inventory` (one-directional; inventory
  does not import cooking, so no cycle).

### `john_whisk/llm.py`
- `suggest_substitution(pantry, title, step, ingredient) -> str` — mirrors
  `suggest_recipe`: builds a strict prompt and calls Ollama; returns "" on
  failure. Prompt: cooking {title}, on step "{step}", missing {ingredient};
  the cook has exactly {pantry}; suggest ONE substitute, prefer something from
  that list, otherwise name a common substitute and say they'd need to get it;
  never claim they have something not listed; one or two short spoken sentences.

### `john_whisk/inventory.py`
- `substitute(title, step, ingredient) -> str` — fetch the pantry
  (`db.get_inventory` + `_format_item`), call `llm.suggest_substitution`,
  fall back to a spoken apology on empty.

### No `main.py` change
Substitution routes through `Kitchen.navigate`, already reached while cooking.
The hands-free noise guard in `main` already lets non-nav in-recipe utterances
through only when recognized; substitution phrases are handled in navigate, so
in wake-gated mode (the default) they work normally.

## Spoken flow

- Cooking pesto, on the pine-nuts step. Cook: "I don't have pine nuts."
  -> "You could use walnuts instead — you've got those. They'll give a similar
  richness." (stays on the step)
- "What can I use instead of buttermilk?" -> "You can stir a little lemon juice
  into regular milk; you'd need lemon, which isn't on your list."
- Parsed ingredient empty (e.g. just "substitute") -> falls through to the
  normal in-recipe question handler.

## Error handling

- `llm.suggest_substitution` returns "" (Ollama down/timeout) -> `inventory
  .substitute` returns "Sorry, I couldn't think of a substitute right now."
- Not cooking -> substitution phrases are never seen by navigate; the general
  grounded handler answers.

## Testing (TDD)

- `_is_substitution`: true for the trigger families, false for "next" / "how hot
  should the pan be".
- `parse_substitution_ingredient`: "what can I use instead of pine nuts" ->
  "pine nuts"; "I don't have any butter" -> "butter"; "I'm out of eggs" ->
  "eggs"; "substitute for buttermilk" -> "buttermilk".
- `llm.suggest_substitution`: pantry + title + step + ingredient all reach the
  prompt; strict-substitute instruction present (HTTP mocked).
- `inventory.substitute`: passes the real pantry; empty LLM -> apology.
- `Kitchen.navigate`: a substitution utterance mid-recipe returns the substitute
  and keeps the session; a normal question still hits `ask_in_recipe`; "next"
  still steps. (`inventory.substitute` monkeypatched.)
- On-device: start a real recipe, ask "what can I use instead of <the missing
  item>", confirm a sensible pantry-preferring answer and that it stays on step.

## Out of scope

- Auto-updating the recipe steps to use the substitute.
- Remembering substitutions across sessions.
- Substitution when not actively cooking (general handler covers it).

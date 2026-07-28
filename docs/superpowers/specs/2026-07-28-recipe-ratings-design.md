# Recipe Ratings & History — Design

Status: approved 2026-07-28. Rate cooked meals (thumbs up/down); suggestions
learn to favor likes and drop dislikes.

## Decisions (from brainstorming)

- **Thumbs up/down** (not 1-5 stars) — enough to favor/drop, easy by voice.
- Implicit rating ("that was great") targets the recipe you just cooked;
  explicit rating names a recipe ("I love chicken alfredo").
- Ratings bias SUGGESTIONS (via the prompt), not hard blocks — you can still
  cook a disliked recipe if you ask for it directly.

## Components

### `john_whisk/ratings.py`
`ratings` table in the pantry DB (`config.DB_PATH`):
`recipe (display title), title_norm (key/dedupe), rating (1 like / -1 dislike),
cooked_count, last_at`.

- `cooked(title)` — record a cook: upsert (title, cooked_count+1, last_at=now).
  Called from `cooking.start`; also defines the "last cooked" recipe.
- `last_cooked()` — display title of the most recently cooked recipe (max
  last_at), or None.
- `rate(title, up: bool)` — upsert the rating (+1/-1) for a title.
- `favorites()` / `disliked()` — titles with rating +1 / -1.
- `preference_clause()` — a clause for the suggest prompt, e.g. "Do not suggest
  sushi or liver. I especially enjoy chicken alfredo and tacos." ("" if none).
- `answer_favorites()` — spoken list of favorites (or "haven't rated any").
- `rate_from_text(text)` — parse sentiment + target and apply:
  - sentiment: +1 for great/love/like/delicious/amazing/good/tasty; -1 for
    bad/hate/terrible/awful/never again/don't suggest/dislike/"didn't like"
    (negatives checked first, since some contain "like"). 0 -> unclear.
  - target: strip rate lead-ins ("i love", "that was", "don't suggest", ...) and
    sentiment/filler words; if what remains is empty or a pronoun ("that"/"it")
    -> `last_cooked()`; else the named dish. Returns (target, sentiment) or None.
- `handle(text)` — favorites query -> `answer_favorites`; else `rate_from_text`
  and confirm ("Glad you liked X — I'll suggest it more." / "Got it — I won't
  suggest X anymore."); unclear -> a gentle re-ask.

### Integration
- `cooking.start` — after building the session, `ratings.cooked(recipe["title"])`
  so the started recipe becomes the implicit rating target.
- `inventory.suggest` — prepend `ratings.preference_clause()` (alongside the
  dietary clause) to the suggest request.
- `router` — `rate` intent: triggers "that was", "i love", "i like", "i liked",
  "i loved", "i don't like", "i didn't like", "i hate", "rate", "don't suggest",
  "never again", "my favorite(s)", "delicious", "what do i like". Precedence
  after cook/plan (so "I would like to make X" stays plan) and before suggest.
- `main` — `rate` -> `ratings.handle(text)`.

## Spoken flow

- (after cooking) "That was great." -> rates the last-cooked recipe up ->
  "Glad you liked Chicken Alfredo — I'll suggest it more."
- "Don't suggest that again." -> last-cooked down -> "Got it — I won't suggest
  Chicken Alfredo anymore."
- "I love tacos." -> rates Tacos up.
- "What are my favorite recipes?" -> "Your favorites are Chicken Alfredo and
  Tacos."
- Later "what can I make" -> the suggest prompt avoids disliked, favors liked.

## Error handling

- No last-cooked and no named target -> "I'm not sure which recipe you mean."
- Unclear sentiment -> gentle re-ask.
- Re-rating a recipe updates it (upsert).

## Testing (TDD)

- store: cooked upsert + last_cooked ordering; rate upsert (+/-); favorites/
  disliked; clear.
- rate_from_text: "that was great" -> last-cooked +1; "I don't like sushi" ->
  sushi -1; "don't suggest that again" -> last-cooked -1; negatives beat the
  embedded "like".
- preference_clause: contains disliked (avoid) + liked (favor); "" when none.
- cooking.start records cooked(title).
- inventory.suggest: preference clause reaches the prompt.
- router: rate vs cook/plan/suggest precedence.
- On-device: cook a real recipe, "that was great" rates it, "what are my
  favorites" reads it, a disliked recipe reaches the suggest prompt as avoid.

## Out of scope

- 1-5 star ratings; ranking the library search by rating; trending/social;
  time-decay of preferences.

# Hands-Free Listening While Cooking — Design

Status: approved 2026-07-27. Phase 2, the deferred fast-follow to step-by-step
recipe guidance ([[recipe-step-guidance-design]]).

## Goal

While a recipe is active, let the cook say navigation commands ("next", "back",
"repeat", "stop", ...) WITHOUT the wake word before each one. A pause never
loses the recipe; it just re-arms the wake word.

## Decisions (resolved during brainstorming)

- **Off-command audio in hands-free mode:** act ONLY on recognized navigation
  commands; silently ignore anything else (a real question OR background noise).
  Free-form questions still work but require the wake word. Chosen for a noisy
  kitchen and to spare the 4GB Pi from running Whisper/LLM on ambient chatter.
- **Listen window:** ~8s after each step before falling back to the wake word.
- **No per-step "listening" beep** (annoying every step).

## Behavior — two listening modes, auto-switched

The main loop carries a `hands_free` flag deciding how the next utterance is
captured:

- **Not cooking** (`session is None`) → wake-gated, unchanged:
  `listener.wait()` -> `audio.chime()` -> `record_until_silence()`.
- **Actively cooking** (`hands_free` true) → skip the wake word; listen directly
  with a short start-timeout. On a command: respond, then listen again.
- **Silence while cooking** (the listen times out) → fall back to wake-gated,
  but KEEP the session. The cook says the wake word once to resume; the next
  cooking turn goes hands-free again.
- **Recipe ends** (stop / past the last step) → `session` becomes None ->
  `hands_free` false -> normal wake-gated mode.

State transitions each turn: after routing, `hands_free = (session is not None)`.
A hands-free capture that returns None sets `hands_free = False` but leaves
`session` untouched (recipe paused, not ended).

## Components

### `john_whisk/audio.py` — add a start-timeout (only audio change)
`record_until_silence(out_path=None, start_timeout_ms=None)`. When
`start_timeout_ms` is set and no speech has STARTED within that many ms, return
None early instead of waiting the full `MAX_UTTERANCE_MS`. Default None keeps
today's behavior. Implementation: `start_timeout_frames = start_timeout_ms //
frame_ms`; in the capture loop, break early when `not started and total >=
start_timeout_frames`. The existing "return None unless started" tail already
turns an early break into a None result.

### `john_whisk/config.py`
`COOK_LISTEN_MS = 8000` — hands-free listen window before falling back to wake.

### `john_whisk/main.py` — extract routing, add the mode loop
- New pure `process_utterance(text, session) -> (reply, session)` holding the
  intent dispatch currently inline in `handle_turn`. Normalizes the tuple order
  (today `cooking.start` returns `(session, reply)` while `cooking.navigate`
  returns `(reply, session)`; the helper returns `(reply, session)` uniformly).
- A `_listen(listener, hands_free)` helper: hands-free ->
  `record_until_silence(start_timeout_ms=config.COOK_LISTEN_MS)`; otherwise
  `listener.wait()` -> chime -> `record_until_silence()`.
- The loop:
  1. `wav = _listen(listener, hands_free)`.
  2. `wav is None`: if hands-free, `hands_free = False` (keep session), continue;
     else speak "I didn't catch that.", continue.
  3. Speak "Let me see." only when NOT hands-free (hands-free nav is instant).
  4. `text = stt.transcribe(wav)`; blank -> re-listen (speak the miss only when
     wake-gated).
  5. **Hands-free guard:** if `hands_free and cooking.classify_nav(text) ==
     "unknown"`, log and ignore (continue) — the noise protection.
  6. `reply, session = process_utterance(text, session)`; speak reply if
     non-empty; `hands_free = session is not None`.
- `handle_turn` is absorbed into the loop (its early-return paths become the
  continue paths above).

## Error handling

- Hands-free capture never blocks forever: the start-timeout guarantees it
  returns within ~8s of silence.
- Exceptions in a turn: keep the existing try/except that logs and speaks
  "Something went wrong, but I'm still here." `session` retains its last value,
  so a recipe survives a transient error.
- Mic contention: hands-free skips `listener.wait()`, so only the recorder opens
  the mic; falling back to wake-gated reuses the existing release-lag handling in
  `_open_mic_stream`.

## Testing

- `process_utterance` is pure -> unit-tested: in-recipe delegates to
  `cooking.navigate`; a cook intent starts a session (returns non-None session);
  a normal intent (e.g. general) returns the reply with `session` unchanged
  (None); tuple order is `(reply, session)` in every branch. Sub-handlers
  monkeypatched.
- Audio timing and the mode loop are hardware-coupled (the existing `audio.py`
  has no unit tests for this reason) -> verified ON-DEVICE, reporting observed
  behavior: (a) start a recipe, step through hands-free with no wake word;
  (b) a >8s pause falls back to the wake word with the recipe intact, then
  resumes hands-free; (c) ambient/unknown speech is ignored mid-recipe;
  (d) "stop" ends the recipe and returns to normal wake-gated mode.

## Out of scope (future)

- Barge-in (interrupting John Whisk while it's speaking a step).
- A configurable/spoken toggle for hands-free on/off.
- Wake-word-free start of a recipe (starting still uses the wake word).

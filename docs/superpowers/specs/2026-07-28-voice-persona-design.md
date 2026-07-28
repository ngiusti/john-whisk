# Voice & Persona — Design

Status: approved 2026-07-28. Male TTS voice + an original deadpan "man of focus"
persona for John Whisk. A delight pass; no functional change to the cooking logic.

## Decisions (from brainstorming)

- **Male voice** — swap the Piper voice from the current female (Amy) to a male
  one; Nicholas picks from a couple of samples by ear.
- **Persona** — a John-Wick-INSPIRED deadpan: terse, dry, unflappable, treats
  cooking like a serious job. ALL lines are ORIGINAL (no movie dialogue — that
  would reproduce copyrighted material). The persona seasons the edges
  (greetings/acks/errors); functional replies ("Added milk") stay clear.

## Components

### Male voice
- Download 1-2 male Piper voices to `~/piper/voices/` (candidates:
  `en_US-ryan-high`, `en_US-joe-medium`, `en_GB-alan-medium`). Generate a short
  spoken sample of each with the existing Piper setup so Nicholas can choose.
- Set `config.PIPER_VOICE` to the chosen `.onnx`. (One-line change; the `.onnx`
  + `.onnx.json` are gitignored like the current voice.)

### `john_whisk/persona.py` — canned flavor lines
Small module of ORIGINAL deadpan lines grouped by moment; `line(moment)` returns
one (varied). Moments:
- `startup` — spoken when the service comes up (replaces "John Whisk is ready.").
- `ack` — the instant "I heard you, working" cue (replaces "Let me see.").
- `signoff` — when a recipe/session stops.
- `error` — the turn-failed message (replaces "Something went wrong...").
- `miss` — didn't-catch-that.
All lines written in-house, e.g. startup: "John Whisk. Let's get to work." /
ack: "On it." / error: "That went sideways. I'm still standing." Kept short and
dry; never a movie quote.

### `config.SYSTEM_PROMPT`
Prepend one persona sentence so conversational LLM replies (general Q&A,
in-recipe questions, flavor tips, substitutions) carry the tone: "You are John
Whisk, a calm, dry-witted, unflappable kitchen assistant who treats cooking like
a professional handling a job — terse and confident." The existing no-fabrication
pantry rules and format rules are KEPT verbatim after it.

### Integration — `john_whisk/main.py`
- `main()` startup: `tts.speak(persona.line("startup"))`.
- wake-gated cue: `tts.speak(persona.line("ack"))` where "Let me see." was.
- turn-failed handler: `persona.line("error")`.
- (didn't-catch-that stays functional but may use `persona.line("miss")`.)

## Testing (TDD)

- `persona.line(moment)` returns a non-empty string from the moment's set for
  every defined moment; unknown moment -> a safe default (or raises clearly).
- lines are short (spoken) and contain no obviously-templated placeholder.
- main still imports; the deterministic replies are unchanged (persona only
  swaps the fixed cue/greeting/error strings).
- On-device: restart -> hear the male voice + a persona startup line; a normal
  turn uses the persona ack; confirm cooking/pantry replies still work.

## Out of scope

- Per-user voice/persona toggle; multiple selectable personas; emotion/prosody.
  (Could add a `config.PERSONA` switch later.)
- Any reproduction of copyrighted film dialogue — explicitly excluded.

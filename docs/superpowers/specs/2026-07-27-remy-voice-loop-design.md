# Remy — Thin Voice Loop (Design)

> Date: 2026-07-27
> Status: Approved design, pre-implementation
> Parent spec: `KITCHEN_ASSISTANT.md` (the overall Kitchen Assistant project)

## Purpose

The first end-to-end milestone of the Kitchen Assistant: a hands-free voice loop
that proves the full pipeline works as one program on the Raspberry Pi 5.

Say **"Hey John Whisk"** → Remy listens → transcribes your speech → asks the local
LLM a cooking question → speaks the answer aloud. Fully offline.

**Deliberately out of scope for this milestone (YAGNI):** inventory/SQLite,
conversation memory between turns, "we're out of X", recipe step-by-step. Those are
the *next* iterations and must not creep into this one.

## Components (all already installed & verified on the Pi)

| Stage | Tool | Notes |
|---|---|---|
| Wake word | Porcupine (`pvporcupine`) | Custom "Hey John Whisk" model; always-listening, tiny footprint. Access key via env var. |
| Speech-to-text | whisper.cpp `whisper-cli` + `ggml-base.en.bin` | ~2.4s for 6s audio. Called as subprocess. |
| LLM | Ollama HTTP API, `llama3.2:3b` | ~5.6 tok/s. **Must send `options.num_ctx=2048`** or it OOMs. Frugal env already set. |
| Text-to-speech | Piper `en_US-amy-medium` | ~6x real-time. Called as subprocess → WAV → `aplay`. |
| End-of-speech | `webrtcvad` | Record until ~0.8s of silence. Hands-free, no fixed cutoff. |

Chosen architecture: **subprocess + HTTP hybrid** (Approach A). Reuses the verified
CLI tools; each stays a separate process, keeping memory low (whisper/piper only
load during a turn) and matching the "separate testable modules" principle.

## Project layout (on the Pi)

```
~/remy/
  venv/                      # Python virtualenv (Debian 13 requires it)
  remy/
    config.py    # device indices (mic hw:2,0, speaker hw:3,0), model paths,
                 #   model names, LLM system prompt, PICOVOICE_ACCESS_KEY from env
    audio.py     # record_until_silence() [webrtcvad], play_wav()
    wake.py      # WakeListener.wait() — blocks until "Hey John Whisk" (pvporcupine)
    stt.py       # transcribe(wav_path) -> str   [shells out to whisper-cli]
    llm.py       # ask(user_text) -> str          [Ollama HTTP API, num_ctx=2048]
    tts.py       # speak(text)                     [piper -> wav -> aplay]
    main.py      # the loop
  models/        # paths to whisper / piper / porcupine models
  tests/         # pytest, no-hardware tests
  run.sh         # dev launcher: activate venv, export key, run main.py
  remy.log       # runtime log
```

Each module answers: what it does, how to call it, what it depends on. Modules are
importable and testable in isolation (e.g. `stt.transcribe()` on a WAV, no mic).

## Data flow (one turn)

```
[always listening]  wake.WakeListener.wait()  ── hears "Hey John Whisk"
      │  (optional short chime so user knows Remy is listening)
      ▼
audio.record_until_silence()  →  /tmp/remy_in.wav   (16kHz mono, stop on ~0.8s silence)
      │
      ▼
stt.transcribe("/tmp/remy_in.wav")  →  user_text
      │
      ▼
llm.ask(user_text)  →  Ollama (system prompt + num_ctx=2048)  →  reply_text
      │
      ▼
tts.speak(reply_text)  →  Piper WAV  →  aplay on hw:3,0
      │
      └────────► back to wake-listening
```

## Configuration & the one secret

- `config.py` centralizes all tunables: ALSA device indices, model file paths,
  Ollama model + `num_ctx`, VAD silence threshold, and the LLM system prompt.
- **Picovoice access key is read from `PICOVOICE_ACCESS_KEY` env var — never
  hardcoded / never committed.** `run.sh` exports it (sourced from an untracked
  `~/remy/.env`, which is gitignored).
- System prompt keeps Remy concise and spoken-friendly: short answers, plain text
  (no markdown/lists that sound wrong when read aloud), kitchen-focused.

## Error handling (loop must survive hours untouched)

Each turn wrapped so no single failure kills the loop:

| Failure | Behavior |
|---|---|
| No speech / silence after wake | Speak "I didn't catch that", re-listen |
| Whisper empty/garbage | Same graceful retry |
| Ollama error/timeout | Speak "Sorry, my brain hiccupped — try again" |
| Unexpected exception | Log to `remy.log`, speak brief apology, continue loop |

## Testing

`pytest` in `tests/`, no hardware required:
- `stt`: known WAV → expected transcript (substring match).
- `llm`: returns non-empty string; respects rough length bound.
- `tts`: produces a valid, non-empty WAV file.
- `config`: loads; key absent raises a clear error.

Audio + wake modules get a manual smoke-test script (needs mic/speaker).

## How it runs (this milestone)

Manual dev launch over SSH: `~/remy/run.sh`, watch `remy.log`. Converting to a
boot-time `systemd` service happens only after the loop works — same staged
approach used for Ollama.

## Prerequisite requiring the user

Porcupine needs a **free Picovoice account**: create the custom "Hey John Whisk"
wake-word model on the Picovoice Console, download the `.ppn` file, and copy the
AccessKey. This is the one manual step; everything else is automatable. The loop
still runs fully offline (the key is validated locally).

# Remy Thin Voice Loop — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a hands-free offline voice loop on the Raspberry Pi 5: say "Hey John Whisk" → Remy transcribes your speech, asks the local LLM a cooking question, and speaks the answer.

**Architecture:** A Python orchestrator (`main.py`) drives four stages, each in its own module: wake word (openWakeWord), speech-to-text (whisper.cpp CLI), LLM (Ollama HTTP API), text-to-speech (Piper CLI). Audio capture/playback go through ALSA via `arecord`/`aplay` subprocesses (no PortAudio). Each module is importable and unit-testable in isolation.

**Tech Stack:** Python 3.13 (venv), openWakeWord + onnxruntime, webrtcvad, requests, pytest. External tools already installed and verified: whisper.cpp (`~/whisper.cpp`), Ollama service (`llama3.2:3b`), Piper (`~/piper`).

**Working context:** All work happens on the Pi at `~/remy` (git repo already initialized). Develop over SSH: `ssh ngiusti@192.168.88.12`. Run commands from inside `~/remy` with the venv active unless noted.

---

## File Structure

| File | Responsibility |
|---|---|
| `remy/config.py` | All constants: device names, model paths, LLM prompt, thresholds. No logic. |
| `remy/stt.py` | `transcribe(wav_path) -> str` via whisper-cli subprocess. |
| `remy/llm.py` | `ask(user_text) -> str` via Ollama HTTP API. |
| `remy/tts.py` | `synthesize(text, out_path)` via Piper; `speak(text)` = synthesize + play. |
| `remy/audio.py` | `record_until_silence(out_path) -> str|None`, `play_wav(path)`. Uses arecord/aplay + webrtcvad. |
| `remy/wake.py` | `WakeListener.wait()` — blocks until wake word (openWakeWord). |
| `remy/main.py` | The loop: wake → record → stt → llm → tts, with per-turn error handling. |
| `run.sh` | Dev launcher: activate venv, run `main.py`. |
| `tests/` | pytest: `test_config.py`, `test_stt.py`, `test_llm.py`, `test_tts.py` + a shared fixture WAV. |

`remy/` will be a package (`remy/__init__.py`). Tests run from `~/remy` so `import remy.stt` works.

---

## Task 1: Python environment & dependencies

**Files:**
- Create: `~/remy/requirements.txt`
- Create: `~/remy/remy/__init__.py` (empty)

- [ ] **Step 1: Create the package marker and requirements file**

`~/remy/remy/__init__.py`: empty file.

`~/remy/requirements.txt`:
```
# openwakeword is installed SEPARATELY with --no-deps to avoid its tflite-runtime
# dependency (no wheel for Python 3.13). It runs on the onnxruntime backend:
#   pip install --no-deps openwakeword==0.6.0
onnxruntime
webrtcvad
requests
numpy
scipy
scikit-learn
tqdm
pytest
setuptools<81      # webrtcvad imports pkg_resources, dropped in setuptools>=81
```

- [ ] **Step 2: Create the venv and install**

Run:
```bash
cd ~/remy
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
./venv/bin/pip install --no-deps openwakeword==0.6.0
```
Expected: all install without error. Prebuilt aarch64 wheels exist for onnxruntime/numpy/scipy/scikit-learn; `webrtcvad` compiles against `build-essential`.
**Why the split:** `openwakeword==0.6.0` hard-requires `tflite-runtime`, which has no wheel for Python 3.13 — so we install its real deps ourselves (above) and add openwakeword `--no-deps`. It runs fine on the onnxruntime backend (Task 7 sets `inference_framework="onnx"`). `setuptools<81` is required because `webrtcvad` imports the now-removed `pkg_resources`.

- [ ] **Step 3: Download openWakeWord base + pretrained models (one-time, needs internet)**

Run:
```bash
cd ~/remy
./venv/bin/python -c "import openwakeword.utils; openwakeword.utils.download_models()"
```
Expected: downloads melspectrogram + embedding models and pretrained wake words (incl. `hey_jarvis`) into the openwakeword package data dir. Prints download progress, exits 0.

- [ ] **Step 4: Verify the toolchain is reachable**

Run:
```bash
cd ~/remy
./venv/bin/python -c "import openwakeword, onnxruntime, webrtcvad, requests, numpy; print('deps ok')"
test -x ~/whisper.cpp/build/bin/whisper-cli && echo whisper ok
test -f ~/whisper.cpp/models/ggml-base.en.bin && echo whisper-model ok
test -x ~/piper/piper && echo piper ok
curl -sf http://localhost:11434/api/tags >/dev/null && echo ollama ok
```
Expected: `deps ok`, `whisper ok`, `whisper-model ok`, `piper ok`, `ollama ok`.

- [ ] **Step 5: Commit**

```bash
cd ~/remy && git add -A && git commit -m "chore: python venv, deps, package skeleton"
```

---

## Task 2: config.py

**Files:**
- Create: `~/remy/remy/config.py`
- Test: `~/remy/tests/test_config.py`

- [ ] **Step 1: Write the failing test**

`~/remy/tests/test_config.py`:
```python
from remy import config

def test_core_constants_present():
    assert config.SAMPLE_RATE == 16000
    assert config.MIC_DEVICE.startswith("plughw:")
    assert config.SPEAKER_DEVICE.startswith("plughw:")
    assert config.NUM_CTX == 2048          # required or the 3B OOMs
    assert "Remy" in config.SYSTEM_PROMPT
    assert config.WAKE_THRESHOLD > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/remy && ./venv/bin/python -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'remy.config'`.

- [ ] **Step 3: Write config.py**

`~/remy/remy/config.py`:
```python
import os

HOME = os.path.expanduser("~")

# --- Audio devices (from `arecord -l` / `aplay -l`) ---
MIC_DEVICE = "plughw:2,0"       # SunFounder USB mic
SPEAKER_DEVICE = "plughw:3,0"   # HONKYOB USB speaker
SAMPLE_RATE = 16000             # whisper + openwakeword both want 16 kHz mono

# --- Whisper (speech-to-text) ---
WHISPER_BIN = os.path.join(HOME, "whisper.cpp/build/bin/whisper-cli")
WHISPER_MODEL = os.path.join(HOME, "whisper.cpp/models/ggml-base.en.bin")
WHISPER_THREADS = 4

# --- Ollama (LLM) ---
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2:3b"
NUM_CTX = 2048        # MUST be set; default context OOMs the 3B on 4GB
NUM_PREDICT = 200     # cap spoken reply length
OLLAMA_TIMEOUT = 60   # seconds

# --- Piper (text-to-speech) ---
PIPER_BIN = os.path.join(HOME, "piper/piper")
PIPER_DIR = os.path.join(HOME, "piper")            # cwd so it finds espeak-ng-data
PIPER_VOICE = os.path.join(HOME, "piper/voices/en_US-amy-medium.onnx")

# --- Wake word (openWakeWord) ---
# Prototype with built-in "hey_jarvis"; swap to a custom .onnx path later.
WAKE_MODEL = "hey_jarvis"
WAKE_THRESHOLD = 0.5
WAKE_INFERENCE_FRAMEWORK = "onnx"   # or "tflite" if onnxruntime unavailable

# --- Voice activity detection (end-of-speech) ---
VAD_AGGRESSIVENESS = 2     # 0-3, higher = more aggressive filtering
SILENCE_MS = 800           # stop after this much trailing silence
MAX_UTTERANCE_MS = 12000   # hard cap on one utterance
MIN_SPEECH_MS = 300        # ignore blips shorter than this

# --- Paths ---
IN_WAV = "/tmp/remy_in.wav"
OUT_WAV = "/tmp/remy_out.wav"
LOG_FILE = os.path.join(HOME, "remy/remy.log")

# --- LLM persona ---
SYSTEM_PROMPT = (
    "You are Remy, a friendly, concise kitchen assistant speaking out loud to a cook. "
    "Answer in 1-3 short spoken sentences. Use plain conversational text only: no "
    "markdown, no bullet points, no numbered lists, no emoji. If asked for a recipe, "
    "give a quick spoken summary, not a full written recipe."
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/remy && ./venv/bin/python -m pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/remy && git add -A && git commit -m "feat: config module with device/model constants"
```

---

## Task 3: stt.py (speech-to-text)

**Files:**
- Create: `~/remy/remy/stt.py`
- Create: `~/remy/tests/conftest.py` (generates a shared 16 kHz fixture WAV)
- Create: `~/remy/tests/test_stt.py`

- [ ] **Step 1: Write a conftest fixture that synthesizes a known-speech WAV**

`~/remy/tests/conftest.py`:
```python
import subprocess, os, pytest
from remy import config

@pytest.fixture(scope="session")
def spoken_wav(tmp_path_factory):
    """A 16kHz mono WAV of a known phrase, made with Piper + ffmpeg (no mic)."""
    d = tmp_path_factory.mktemp("audio")
    raw = os.path.join(d, "piper.wav")
    out = os.path.join(d, "spoken16k.wav")
    subprocess.run(
        [config.PIPER_BIN, "--model", config.PIPER_VOICE, "--output_file", raw],
        input=b"testing one two three", cwd=config.PIPER_DIR, check=True,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-i", raw, "-ar", "16000", "-ac", "1", out],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return out
```

- [ ] **Step 2: Write the failing test**

`~/remy/tests/test_stt.py`:
```python
from remy import stt

def test_transcribe_known_phrase(spoken_wav):
    text = stt.transcribe(spoken_wav).lower()
    assert "testing" in text or "one" in text
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd ~/remy && ./venv/bin/python -m pytest tests/test_stt.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'remy.stt'`.

- [ ] **Step 4: Write stt.py**

`~/remy/remy/stt.py`:
```python
import subprocess
from remy import config

def transcribe(wav_path: str) -> str:
    """Transcribe a 16kHz mono WAV to text using whisper.cpp. Returns '' on failure."""
    try:
        result = subprocess.run(
            [config.WHISPER_BIN, "-m", config.WHISPER_MODEL,
             "-f", wav_path, "-nt", "-t", str(config.WHISPER_THREADS)],
            capture_output=True, text=True, timeout=60,
        )
    except (subprocess.SubprocessError, OSError):
        return ""
    return result.stdout.strip()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd ~/remy && ./venv/bin/python -m pytest tests/test_stt.py -v`
Expected: PASS (whisper transcribes the synthesized phrase; substring match tolerates minor differences).

- [ ] **Step 6: Commit**

```bash
cd ~/remy && git add -A && git commit -m "feat: stt module (whisper.cpp wrapper) + fixture"
```

---

## Task 4: llm.py (Ollama)

**Files:**
- Create: `~/remy/remy/llm.py`
- Create: `~/remy/tests/test_llm.py`

- [ ] **Step 1: Write the failing test**

`~/remy/tests/test_llm.py`:
```python
from remy import llm

def test_ask_returns_nonempty_text():
    reply = llm.ask("In one short sentence, what can I cook with eggs?")
    assert isinstance(reply, str)
    assert len(reply.strip()) > 0

def test_ask_handles_empty_input():
    assert llm.ask("") == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/remy && ./venv/bin/python -m pytest tests/test_llm.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'remy.llm'`.

- [ ] **Step 3: Write llm.py**

`~/remy/remy/llm.py`:
```python
import requests
from remy import config

def ask(user_text: str) -> str:
    """Send user text to Ollama and return the reply. Returns '' on empty input/failure."""
    if not user_text or not user_text.strip():
        return ""
    payload = {
        "model": config.OLLAMA_MODEL,
        "prompt": user_text,
        "system": config.SYSTEM_PROMPT,
        "stream": False,
        "options": {"num_ctx": config.NUM_CTX, "num_predict": config.NUM_PREDICT},
    }
    try:
        r = requests.post(config.OLLAMA_URL, json=payload, timeout=config.OLLAMA_TIMEOUT)
        r.raise_for_status()
        return r.json().get("response", "").strip()
    except (requests.RequestException, ValueError):
        return ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/remy && ./venv/bin/python -m pytest tests/test_llm.py -v`
Expected: PASS (Ollama service is running; first call may take ~26s cold-load).

- [ ] **Step 5: Commit**

```bash
cd ~/remy && git add -A && git commit -m "feat: llm module (Ollama HTTP wrapper)"
```

---

## Task 5: tts.py (Piper)

**Files:**
- Create: `~/remy/remy/tts.py`
- Create: `~/remy/tests/test_tts.py`

- [ ] **Step 1: Write the failing test**

`~/remy/tests/test_tts.py`:
```python
import wave
from remy import tts

def test_synthesize_produces_valid_wav(tmp_path):
    out = str(tmp_path / "out.wav")
    path = tts.synthesize("Hello from Remy.", out)
    assert path == out
    with wave.open(out, "rb") as w:
        assert w.getnframes() > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/remy && ./venv/bin/python -m pytest tests/test_tts.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'remy.tts'`.

- [ ] **Step 3: Write tts.py**

`~/remy/remy/tts.py`:
```python
import subprocess
from remy import config

def synthesize(text: str, out_path: str = None) -> str:
    """Render text to a WAV file with Piper. Returns the WAV path."""
    out_path = out_path or config.OUT_WAV
    subprocess.run(
        [config.PIPER_BIN, "--model", config.PIPER_VOICE, "--output_file", out_path],
        input=text.encode("utf-8"), cwd=config.PIPER_DIR, check=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return out_path

def speak(text: str) -> None:
    """Synthesize text and play it through the speaker."""
    if not text or not text.strip():
        return
    from remy import audio          # lazy import: keeps this module usable before Task 6
    path = synthesize(text)
    audio.play_wav(path)
```

Note: `audio` is imported lazily inside `speak()`, so `test_tts.py` (which only calls `synthesize`) passes even though `audio.py` is written in Task 6. No import ordering dependency.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/remy && ./venv/bin/python -m pytest tests/test_tts.py -v`
Expected: PASS.
(If `import remy.audio` fails because Task 6 isn't written yet, do Task 6 first, then return here.)

- [ ] **Step 5: Commit**

```bash
cd ~/remy && git add -A && git commit -m "feat: tts module (Piper wrapper)"
```

---

## Task 6: audio.py (record + play)

**Files:**
- Create: `~/remy/remy/audio.py`
- Create: `~/remy/scripts/smoke_audio.py` (manual, needs mic + speaker)

- [ ] **Step 1: Write audio.py**

`~/remy/remy/audio.py`:
```python
import subprocess, wave, contextlib
import webrtcvad
from remy import config

def play_wav(path: str) -> None:
    """Play a WAV file through the configured speaker."""
    subprocess.run(["aplay", "-D", config.SPEAKER_DEVICE, path],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

def _write_wav(path, pcm_bytes):
    with contextlib.closing(wave.open(path, "wb")) as w:
        w.setnchannels(1)
        w.setsampwidth(2)          # S16_LE
        w.setframerate(config.SAMPLE_RATE)
        w.writeframes(pcm_bytes)

def record_until_silence(out_path: str = None):
    """Record from the mic until ~SILENCE_MS of trailing silence after speech.
    Returns out_path if speech was captured, else None.
    Streams raw PCM from arecord and gates with webrtcvad (30ms frames)."""
    out_path = out_path or config.IN_WAV
    vad = webrtcvad.Vad(config.VAD_AGGRESSIVENESS)
    frame_ms = 30
    frame_bytes = int(config.SAMPLE_RATE * frame_ms / 1000) * 2   # 960 bytes
    max_frames = config.MAX_UTTERANCE_MS // frame_ms
    silence_frames_needed = config.SILENCE_MS // frame_ms
    min_speech_frames = config.MIN_SPEECH_MS // frame_ms

    proc = subprocess.Popen(
        ["arecord", "-D", config.MIC_DEVICE, "-f", "S16_LE",
         "-r", str(config.SAMPLE_RATE), "-c", "1", "-t", "raw", "-q"],
        stdout=subprocess.PIPE,
    )
    collected = bytearray()
    voiced_frames = 0
    trailing_silence = 0
    started = False
    total = 0
    try:
        while total < max_frames:
            frame = proc.stdout.read(frame_bytes)
            if len(frame) < frame_bytes:
                break
            total += 1
            is_speech = vad.is_speech(frame, config.SAMPLE_RATE)
            if is_speech:
                started = True
                voiced_frames += 1
                trailing_silence = 0
                collected.extend(frame)
            elif started:
                trailing_silence += 1
                collected.extend(frame)
                if trailing_silence >= silence_frames_needed:
                    break
    finally:
        proc.terminate()
        proc.wait()

    if not started or voiced_frames < min_speech_frames:
        return None
    _write_wav(out_path, bytes(collected))
    return out_path
```

- [ ] **Step 2: Write the manual smoke-test script**

`~/remy/scripts/smoke_audio.py`:
```python
"""Manual test (needs mic + speaker): records until you stop talking, plays it back."""
from remy import audio

print("Speak after this line prints; stop when done...")
path = audio.record_until_silence()
if path:
    print("Captured:", path, "-> playing back")
    audio.play_wav(path)
else:
    print("No speech detected.")
```

- [ ] **Step 3: Run the smoke test manually**

Run: `cd ~/remy && ./venv/bin/python -m scripts.smoke_audio`
Then speak a sentence and stop. Expected: it prints "Captured", then you hear your voice played back. It should stop on its own shortly after you stop talking.

- [ ] **Step 4: Commit**

```bash
cd ~/remy && git add -A && git commit -m "feat: audio module (arecord+VAD capture, aplay playback)"
```

---

## Task 7: wake.py (openWakeWord)

**Files:**
- Create: `~/remy/remy/wake.py`
- Create: `~/remy/scripts/smoke_wake.py` (manual, needs mic)

- [ ] **Step 1: Write wake.py**

`~/remy/remy/wake.py`:
```python
import subprocess
import numpy as np
from openwakeword.model import Model
from remy import config

class WakeListener:
    """Blocks until the wake word is heard on the mic (openWakeWord)."""

    CHUNK_SAMPLES = 1280          # openWakeWord expects 80ms @ 16kHz
    CHUNK_BYTES = CHUNK_SAMPLES * 2

    def __init__(self):
        self.model = Model(
            wakeword_models=[config.WAKE_MODEL],
            inference_framework=config.WAKE_INFERENCE_FRAMEWORK,
        )
        self.threshold = config.WAKE_THRESHOLD

    def wait(self) -> None:
        """Return once the wake word crosses the detection threshold."""
        self.model.reset()
        proc = subprocess.Popen(
            ["arecord", "-D", config.MIC_DEVICE, "-f", "S16_LE",
             "-r", str(config.SAMPLE_RATE), "-c", "1", "-t", "raw", "-q"],
            stdout=subprocess.PIPE,
        )
        try:
            while True:
                data = proc.stdout.read(self.CHUNK_BYTES)
                if len(data) < self.CHUNK_BYTES:
                    break
                audio = np.frombuffer(data, dtype=np.int16)
                scores = self.model.predict(audio)
                if max(scores.values()) >= self.threshold:
                    return
        finally:
            proc.terminate()
            proc.wait()
```

- [ ] **Step 2: Write the manual smoke-test script**

`~/remy/scripts/smoke_wake.py`:
```python
"""Manual test (needs mic): prints when the wake word is detected."""
from remy.wake import WakeListener

print("Loading wake model...")
w = WakeListener()
print("Say the wake word ('hey jarvis' for the prototype model)...")
w.wait()
print("WAKE WORD DETECTED!")
```

- [ ] **Step 3: Run the smoke test manually**

Run: `cd ~/remy && ./venv/bin/python -m scripts.smoke_wake`
Then say "hey jarvis". Expected: prints "WAKE WORD DETECTED!" within a second of you saying it. Try staying silent first to confirm it does NOT false-trigger.

- [ ] **Step 4: Commit**

```bash
cd ~/remy && git add -A && git commit -m "feat: wake module (openWakeWord listener)"
```

---

## Task 8: main.py loop + run.sh (end-to-end)

**Files:**
- Create: `~/remy/remy/main.py`
- Create: `~/remy/run.sh`

- [ ] **Step 1: Write main.py**

`~/remy/remy/main.py`:
```python
import logging
from remy import config, wake, audio, stt, llm, tts

logging.basicConfig(
    filename=config.LOG_FILE, level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("remy")

def handle_turn(listener):
    listener.wait()                      # blocks until wake word
    log.info("wake word detected")
    wav = audio.record_until_silence()
    if not wav:
        tts.speak("I didn't catch that.")
        return
    text = stt.transcribe(wav)
    log.info("heard: %s", text)
    if not text.strip():
        tts.speak("I didn't catch that.")
        return
    reply = llm.ask(text)
    log.info("reply: %s", reply)
    if not reply.strip():
        tts.speak("Sorry, my brain hiccupped. Try again.")
        return
    tts.speak(reply)

def main():
    log.info("Remy starting up")
    listener = wake.WakeListener()
    print("Remy is listening. Say the wake word.")
    while True:
        try:
            handle_turn(listener)
        except KeyboardInterrupt:
            print("\nShutting down.")
            break
        except Exception:
            log.exception("turn failed")
            try:
                tts.speak("Something went wrong, but I'm still here.")
            except Exception:
                log.exception("could not speak error")

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write run.sh**

`~/remy/run.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
exec ./venv/bin/python -m remy.main
```
Then: `chmod +x ~/remy/run.sh`

- [ ] **Step 3: Full manual end-to-end test**

Run: `cd ~/remy && ./run.sh`
Then: say "hey jarvis", wait for it to start listening, ask "what can I make with chicken and rice?", stop talking.
Expected: within a few seconds Remy speaks a short recipe suggestion. Check `~/remy/remy.log` for the wake/heard/reply trace. Press Ctrl+C to stop.

- [ ] **Step 4: Commit**

```bash
cd ~/remy && git add -A && git commit -m "feat: main loop + run.sh (end-to-end voice loop)"
```

---

## Task 9: Run the full test suite

- [ ] **Step 1: Run all non-hardware tests together**

Run: `cd ~/remy && ./venv/bin/python -m pytest -v`
Expected: `test_config`, `test_stt`, `test_llm`, `test_tts` all PASS.

- [ ] **Step 2: Commit any fixups**

```bash
cd ~/remy && git add -A && git commit -m "test: full suite green" || echo "nothing to commit"
```

---

## Deferred (NOT in this plan — next iterations)

- Custom "Hey John Whisk" model (train in Colab, drop in `models/`, set `WAKE_MODEL`).
- systemd service for boot auto-start.
- Inventory/SQLite, conversation memory, "we're out of X", recipe step-through.
- "Listening" chime after wake word.

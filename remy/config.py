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

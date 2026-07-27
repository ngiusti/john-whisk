import os

HOME = os.path.expanduser("~")

# --- Audio devices ---
# Use stable ALSA card NAMES, not numbers: USB card numbers shuffle across reboots
# (mic/speaker swapped between 2/3 on a reboot). Names are tied to the USB device.
#   arecord -L / aplay -L  ->  plughw:CARD=<id>,DEV=0     ( ids from /proc/asound/cards )
MIC_DEVICE = "plughw:CARD=Device,DEV=0"          # USB PnP Sound Device (C-Media) — mic
SPEAKER_DEVICE = "plughw:CARD=UACDemoV10,DEV=0"   # UACDemoV1.0 (Jieli) — speaker
SPEAKER_CARD = "UACDemoV10"                        # `amixer -c <card>` for volume control
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
NUM_PREDICT_RECIPE = 600   # recipes are longer than a one-off spoken reply
OLLAMA_TIMEOUT = 60   # seconds

# --- Piper (text-to-speech) ---
PIPER_BIN = os.path.join(HOME, "piper/piper")
PIPER_DIR = os.path.join(HOME, "piper")            # cwd so it finds espeak-ng-data
PIPER_VOICE = os.path.join(HOME, "piper/voices/en_US-amy-medium.onnx")

# --- Wake word (openWakeWord) ---
# Prototype with built-in "hey_jarvis"; swap to the custom "Hey John Whisk" .onnx path.
WAKE_MODEL = "hey_jarvis"
WAKE_THRESHOLD = 0.5
WAKE_INFERENCE_FRAMEWORK = "onnx"   # or "tflite" if onnxruntime unavailable

# --- Voice activity detection (end-of-speech) ---
VAD_AGGRESSIVENESS = 2     # 0-3, higher = more aggressive filtering
SILENCE_MS = 5000          # stop after this much trailing silence (tolerates long pauses)
MAX_UTTERANCE_MS = 25000   # hard cap on one utterance (raised to fit long pause-filled speech)
MIN_SPEECH_MS = 300        # ignore blips shorter than this

# --- Paths ---
IN_WAV = "/tmp/john_whisk_in.wav"
OUT_WAV = "/tmp/john_whisk_out.wav"
LOG_FILE = os.path.join(HOME, "john-whisk/john_whisk.log")

# --- LLM persona ---
SYSTEM_PROMPT = (
    "You are John Whisk, a friendly, concise kitchen assistant speaking out loud to a "
    "cook. Answer in 1-3 short spoken sentences. Use plain conversational text only: no "
    "markdown, no bullet points, no numbered lists, no emoji. If asked for a recipe, "
    "give a quick spoken summary, not a full written recipe."
)

# --- Inventory (Phase 2) ---
DB_PATH = os.path.join(HOME, "john-whisk/john_whisk.db")

EXTRACT_PROMPT = (
    "The user just told you which groceries they bought. Extract each food item they "
    "mention. Respond with ONLY JSON of the form "
    '{"items": [{"name": <singular lowercase string>, "quantity": <number or null>, '
    '"unit": <string or null>}]}. '
    "Set quantity to null UNLESS the user explicitly says a number for that item. "
    "Never invent, guess, or default a quantity. "
    'Examples: "chicken and eggs" -> both quantity null; "a dozen eggs" -> eggs quantity 12; '
    '"2 bacon" -> bacon quantity 2; "some spinach" -> spinach quantity null. '
    "Convert number words to digits (a dozen = 12, a couple = 2, a few = 3, half a dozen = 6). "
    "Only extract items the user explicitly says they bought or have. If the text is a "
    'question, a request, or does not clearly list groceries, return {"items": []}. '
    "Never invent items that were not mentioned."
)

# --- Recipe guidance (Phase 2) ---
RECIPE_PROMPT = (
    "You are a cooking assistant. The user names a dish; give a simple recipe for it. "
    "Respond in EXACTLY this format and nothing else:\n"
    "INGREDIENTS: <comma-separated ingredients with rough quantities>\n"
    "STEPS:\n"
    "1. <short imperative step>\n"
    "2. <short imperative step>\n"
    "Use between 3 and 12 steps, one per line, each a single short sentence. "
    "No markdown, no extra commentary before or after the list."
)

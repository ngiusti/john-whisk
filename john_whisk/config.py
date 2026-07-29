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
PIPER_VOICE = os.path.join(HOME, "piper/voices/en_GB-alan-medium.onnx")

# --- Wake word (openWakeWord) ---
# Custom-trained "Hey John Whisk" model (models/hey_john_whisk.onnx). To fall back
# to the built-in prototype, set WAKE_MODEL = "hey_jarvis".
WAKE_MODEL = os.path.join(HOME, "john-whisk/models/hey_john_whisk.onnx")
WAKE_THRESHOLD = 0.5
WAKE_INFERENCE_FRAMEWORK = "onnx"   # or "tflite" if onnxruntime unavailable

# --- Voice activity detection (end-of-speech) ---
VAD_AGGRESSIVENESS = 3     # 0-3, higher = more aggressive filtering (3 rejects more
                           # background noise so the Pi fan / kitchen doesn't read as speech)
SILENCE_MS = 5000          # stop after this much trailing silence (tolerates long pauses)
MAX_UTTERANCE_MS = 25000   # hard cap on one utterance (raised to fit long pause-filled speech)
MIN_SPEECH_MS = 300        # ignore blips shorter than this
# Hands-free (between recipe steps): tighter windows than the wake-gated defaults,
# since commands are short ("next", "back") and responsiveness matters most here.
HANDS_FREE_COOKING = False  # if True, skip the wake word between recipe steps. Off by
                            # preference: saying "Hey Jarvis" each time is more natural and
                            # the wake detector is far more noise-robust than raw VAD.
COOK_LISTEN_MS = 6000      # listen this long for a command before re-arming the wake word
COOK_MAX_UTTERANCE_MS = 5000   # cap a single hands-free capture (a noise-triggered clip
                               # ends in ~5s instead of holding the mic for the full 25s)
COOK_SILENCE_MS = 1500     # finalize a hands-free command after this much trailing silence
                           # (snappier than the 5s wake-gated pause)

# --- Paths ---
IN_WAV = "/tmp/john_whisk_in.wav"
OUT_WAV = "/tmp/john_whisk_out.wav"
LOG_FILE = os.path.join(HOME, "john-whisk/john_whisk.log")

# --- LLM persona ---
SYSTEM_PROMPT = (
    "You are John Whisk, a calm, dry-witted, unflappable kitchen assistant speaking out "
    "loud to a cook. You treat cooking like a professional handling a job: terse, "
    "confident, a little deadpan, never fussy or bubbly. "
    "Answer in 1-3 short spoken sentences. Use plain conversational text only: no "
    "markdown, no bullet points, no numbered lists, no emoji. If asked for a recipe, "
    "give a quick spoken summary, not a full written recipe. "
    "IMPORTANT: You do NOT know what food is in the user's kitchen, fridge, or pantry "
    "unless it is stated in their message. Never claim, guess, or list what they have "
    "in stock from memory, and never invent ingredients they own. If they ask what they "
    "have or whether they have a specific item, tell them to say 'what do I have' or to "
    "ask 'do we have' followed by the item, so you can check their logged pantry."
)

# --- Inventory (Phase 2) ---
DB_PATH = os.path.join(HOME, "john-whisk/john_whisk.db")

# --- Phone/web dashboard ---
WEB_HOST = "0.0.0.0"        # bind to the LAN (home network only; no external exposure)
WEB_PORT = 8080

# --- Recipe store + importers (Phase 2) ---
# Separate DB so the bulk recipe library is independent of pantry state.
RECIPES_DB_PATH = os.path.join(HOME, "john-whisk/recipes.db")
RECIPE_MATCH_THRESHOLD = 0.5      # min title similarity (0-1) for a stored-recipe hit
IMPORT_USER_AGENT = ("JohnWhiskRecipeImporter/1.0 "
                     "(https://github.com/ngiusti/john-whisk; personal kitchen assistant)")
IMPORT_RATE_LIMIT_S = 2.5         # seconds between requests when crawling a site
IMPORT_MAX_RECIPES = 50           # cap per site crawl

# Fixed category set — the LLM must pick from these so category queries are
# reliable (everything saucy lands in "sauce", not scattered synonyms).
CATEGORIES = [
    "sauce", "pasta", "vegetable", "fruit", "protein", "dairy", "grain",
    "spice", "condiment", "beverage", "baking", "oil", "legume", "nuts",
    "herb", "other",
]

EXTRACT_PROMPT = (
    "The user just told you which groceries they bought. Extract each food item they "
    "mention. Respond with ONLY JSON of the form "
    '{"items": [{"name": <singular lowercase string>, "quantity": <number or null>, '
    '"unit": <string or null>, "category": <one category string>}]}. '
    "Set quantity to null UNLESS the user explicitly says a number for that item. "
    "Never invent, guess, or default a quantity. "
    'Examples: "chicken and eggs" -> both quantity null; "a dozen eggs" -> eggs quantity 12; '
    '"2 bacon" -> bacon quantity 2; "some spinach" -> spinach quantity null. '
    "Convert number words to digits (a dozen = 12, a couple = 2, a few = 3, half a dozen = 6). "
    "For category, choose EXACTLY ONE from this list and nothing else: "
    "sauce, pasta, vegetable, fruit, protein, dairy, grain, spice, condiment, beverage, "
    "baking, oil, legume, nuts, herb, other. Use protein for meat/fish/eggs/tofu, grain "
    "for bread/rice/cereal, spice for dried seasonings, herb for fresh herbs, oil for oils "
    "and fats, and other if nothing fits. "
    'Examples: marinara -> sauce; penne -> pasta; chicken -> protein; spinach -> vegetable; '
    'ketchup -> condiment; flour -> baking; olive oil -> oil; black beans -> legume. '
    "Only extract items the user explicitly says they bought or have. If the text is a "
    'question, a request, or does not clearly list groceries, return {"items": []}. '
    "Never invent items that were not mentioned."
)

# --- Recipe suggestion (Phase 2) — strict pantry rule ---
# The hard rule: only suggest from what is actually logged; never invent owned items.
SUGGEST_PROMPT = (
    "You are John Whisk suggesting what to cook. The user's message contains the "
    "EXACT and COMPLETE list of ingredients they currently have. Follow these rules "
    "strictly and without exception: "
    "1) Assume they have ONLY the ingredients on that list, plus basic salt, pepper, "
    "and water. Nothing else exists in their kitchen. "
    "2) NEVER state or imply they already have any ingredient that is not on the list. "
    "Do not invent, assume, or add pantry items. "
    "3) Suggest one or two simple recipes they can make mostly or entirely from the "
    "listed items. "
    "4) If a recipe would need an ingredient that is not on the list, you may mention "
    "it, but you MUST clearly say they would need to buy it first. "
    "Answer in one to three short spoken sentences, plain conversational text, no lists."
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

# --- Nutrition (Phase 2) ---
NUTRITION_SEED_PATH = os.path.join(HOME, "john-whisk/data/nutrition.json")
DEFAULT_SERVINGS = 4          # assumed servings when a recipe states none
NUTRITION_ESTIMATE_PROMPT = (
    "Estimate the nutrition for the food described by the user. Respond with ONLY "
    'JSON of the form {"calories": <number>, "protein": <grams>, "carbs": <grams>, '
    '"fat": <grams>} for the ENTIRE amount described, using typical values. '
    "Numbers only, no units in the values, and no text before or after the JSON."
)

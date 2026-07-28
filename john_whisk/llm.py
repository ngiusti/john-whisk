import json
import re
import requests
from john_whisk import config


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


def _parse_recipe(title: str, text: str):
    """Turn the model's INGREDIENTS/STEPS reply into a recipe dict, or None if
    fewer than two steps could be parsed (garbage / format not followed)."""
    ingredients = ""
    steps = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"(?i)^ingredients\s*:\s*(.+)$", line)
        if m:
            ingredients = m.group(1).strip()
            continue
        m = re.match(r"^\d+[.)]\s*(.+)$", line)
        if m:
            steps.append(m.group(1).strip())
    if len(steps) < 2:
        return None
    return {"title": title, "ingredients": ingredients, "steps": steps}


def generate_recipe(dish: str):
    """Ask the LLM for a recipe for `dish`. Returns {title, ingredients, steps}
    or None on empty input, request failure, or an unparseable reply."""
    if not dish or not dish.strip():
        return None
    dish = dish.strip()
    payload = {
        "model": config.OLLAMA_MODEL,
        "prompt": f"Give a recipe for {dish}.",
        "system": config.RECIPE_PROMPT,
        "stream": False,
        "options": {"num_ctx": config.NUM_CTX, "num_predict": config.NUM_PREDICT_RECIPE},
    }
    try:
        r = requests.post(config.OLLAMA_URL, json=payload, timeout=config.OLLAMA_TIMEOUT)
        r.raise_for_status()
        text = r.json().get("response", "")
    except (requests.RequestException, ValueError):
        return None
    return _parse_recipe(dish, text)


def ask_grounded(text: str, pantry: str) -> str:
    """Like ask(), but injects the user's ACTUAL pantry into the system prompt so
    inventory-adjacent questions are answered from real data instead of invented
    items. Grounding beats prohibition: a 3B model told 'you don't know the
    pantry' still fabricates; given the real list, it answers truthfully."""
    if not text or not text.strip():
        return ""
    if pantry:
        stock_line = (
            f"For reference, the user's kitchen contains EXACTLY these items and nothing "
            f"else (plus basic salt, pepper, and water): {pantry}. "
        )
    else:
        stock_line = (
            "For reference, the user has logged no pantry items, so treat their kitchen "
            "as empty apart from basic salt, pepper, and water. "
        )
    system = (
        config.SYSTEM_PROMPT + " " + stock_line +
        "If they ask what they have or about a specific item, answer ONLY from that list "
        "and never invent, guess, or assume items they own."
    )
    payload = {
        "model": config.OLLAMA_MODEL,
        "prompt": text,
        "system": system,
        "stream": False,
        "options": {"num_ctx": config.NUM_CTX, "num_predict": config.NUM_PREDICT},
    }
    try:
        r = requests.post(config.OLLAMA_URL, json=payload, timeout=config.OLLAMA_TIMEOUT)
        r.raise_for_status()
        return r.json().get("response", "").strip()
    except (requests.RequestException, ValueError):
        return ""


def suggest_recipe(pantry: str, request: str) -> str:
    """Suggest recipes constrained to the pantry. The strict SUGGEST_PROMPT is
    the authoritative rule: only the listed items are on hand, and the model may
    not imply the user owns anything else. Returns '' on failure."""
    prompt = f"The exact and complete list of ingredients I have is: {pantry}. {request}"
    payload = {
        "model": config.OLLAMA_MODEL,
        "prompt": prompt,
        "system": config.SUGGEST_PROMPT,
        "stream": False,
        "options": {"num_ctx": config.NUM_CTX, "num_predict": config.NUM_PREDICT},
    }
    try:
        r = requests.post(config.OLLAMA_URL, json=payload, timeout=config.OLLAMA_TIMEOUT)
        r.raise_for_status()
        return r.json().get("response", "").strip()
    except (requests.RequestException, ValueError):
        return ""


def ask_in_recipe(title: str, step: str, question: str) -> str:
    """Answer a mid-recipe question with the current step as context, so the
    cook doesn't have to leave recipe mode to ask something."""
    prompt = (
        f"You are guiding me through cooking {title}. "
        f'I am currently on this step: "{step}". '
        f"I asked: {question} Answer briefly for a cook in the middle of the recipe."
    )
    return ask(prompt)


def extract_items(text: str):
    """Ask the LLM to extract grocery items+quantities as JSON. Returns a list of
    {name, quantity, unit} dicts (normalized), or [] on any failure."""
    payload = {
        "model": config.OLLAMA_MODEL,
        "prompt": text,
        "system": config.EXTRACT_PROMPT,
        "stream": False,
        "format": "json",
        "options": {"num_ctx": config.NUM_CTX, "num_predict": config.NUM_PREDICT},
    }
    try:
        r = requests.post(config.OLLAMA_URL, json=payload, timeout=config.OLLAMA_TIMEOUT)
        r.raise_for_status()
        data = json.loads(r.json().get("response", ""))
        raw_items = data.get("items", [])
    except (requests.RequestException, ValueError, TypeError, KeyError):
        return []
    result = []
    for it in raw_items:
        if not isinstance(it, dict):
            continue
        name = it.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        qty = it.get("quantity")
        if not isinstance(qty, (int, float)) or isinstance(qty, bool):
            qty = None
        unit = it.get("unit")
        if not isinstance(unit, str) or not unit.strip():
            unit = None
        category = it.get("category")
        if not isinstance(category, str) or category.strip().lower() not in config.CATEGORIES:
            category = "other"
        else:
            category = category.strip().lower()
        result.append({"name": name.strip().lower(), "quantity": qty, "unit": unit,
                       "category": category})
    return result

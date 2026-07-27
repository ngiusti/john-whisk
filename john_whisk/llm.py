import json
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
        result.append({"name": name.strip().lower(), "quantity": qty, "unit": unit})
    return result

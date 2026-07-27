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

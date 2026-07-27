import re
import subprocess
from john_whisk import config

_WORD_NUMBERS = {
    "zero": 0, "ten": 10, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    "one hundred": 100, "a hundred": 100, "hundred": 100,
    "full": 100, "max": 100, "maximum": 100, "mute": 0,
}


def parse_percent(text):
    """Extract a 0-100 volume level from text (digits or common words). None if absent."""
    m = re.search(r"\d{1,3}", text)
    if m:
        return max(0, min(100, int(m.group(0))))
    t = text.lower()
    for word, val in _WORD_NUMBERS.items():
        if word in t:
            return val
    return None


def set_volume(pct: int) -> str:
    """Set the speaker volume to pct% (immediate) and persist it. Returns a confirmation."""
    pct = max(0, min(100, pct))
    subprocess.run(
        ["amixer", "-c", config.SPEAKER_CARD, "sset", "PCM", f"{pct}%"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    )
    # persist across reboots (best-effort; needs passwordless sudo, harmless if it fails)
    subprocess.run(
        ["sudo", "-n", "alsactl", "store"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    )
    return f"Volume set to {pct} percent."


def set_from_text(text: str) -> str:
    pct = parse_percent(text)
    if pct is None:
        return "Sorry, I didn't catch the volume level."
    return set_volume(pct)

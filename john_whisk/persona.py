"""John Whisk's persona: short, dry, unflappable canned lines for fixed moments
(startup / ack / signoff / error / miss). Original writing — a calm-professional
deadpan that treats cooking like a job. Functional replies live elsewhere; this
only seasons the edges."""
import random

LINES = {
    "startup": [
        "John Whisk. Ready to work.",
        "John Whisk here. Let's get to work.",
        "Kitchen's open. Tell me what you need.",
        "I'm listening. Let's cook.",
    ],
    "ack": [
        "On it.",
        "Working.",
        "Consider it handled.",
        "Give me a second.",
    ],
    "signoff": [
        "Done. Clean as you go.",
        "That's a wrap. Nicely done.",
        "Kitchen's yours. I'll be here.",
    ],
    "error": [
        "That went sideways. I'm still standing.",
        "Something slipped. Try me again.",
        "Hit a snag. I'm not going anywhere.",
    ],
    "miss": [
        "Didn't catch that.",
        "Say that again for me.",
        "Missed it. One more time.",
    ],
}


def line(moment):
    """A random persona line for a moment; a safe fallback for unknown moments."""
    return random.choice(LINES.get(moment) or ["Okay."])

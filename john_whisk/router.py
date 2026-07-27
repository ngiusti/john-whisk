SUGGEST_TRIGGERS = [
    "what can i make", "what can i cook", "what should i", "suggest", "recipe",
    "what's for dinner", "whats for dinner", "ideas for dinner", "make with",
]
ADD_TRIGGERS = [
    "bought", "grabbed", "picked up", "purchased", "just got", "stock up",
    "i have", "we have", " got ", "add ",
]


def classify(text: str) -> str:
    """Return 'add', 'suggest', or 'general'. Precedence: suggest -> add -> general."""
    t = " " + text.lower().strip() + " "
    if any(k in t for k in SUGGEST_TRIGGERS):
        return "suggest"
    if any(k in t for k in ADD_TRIGGERS):
        return "add"
    return "general"

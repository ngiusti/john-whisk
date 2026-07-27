SUGGEST_TRIGGERS = [
    "what can i make", "what can i cook", "what should i", "suggest", "recipe",
    "what's for dinner", "whats for dinner", "ideas for dinner", "make with",
]
LIST_TRIGGERS = [
    "what do i have", "what have i got", "what's in my", "whats in my",
    "what do i have left", "what's in stock", "whats in stock",
    "what's in the fridge", "whats in the fridge", "what's in the pantry",
    "whats in the pantry", "list my", "my inventory", "in my pantry",
    "what's in my pantry", "do i have",
]
ADD_TRIGGERS = [
    "bought", "grabbed", "picked up", "purchased", "just got", "stock up",
    " got ", "add ",
]


def classify(text: str) -> str:
    """Return 'volume', 'add', 'suggest', 'list', or 'general'.
    Precedence: volume -> suggest -> list -> add -> general."""
    t = " " + text.lower().strip() + " "
    if "volume" in t:
        return "volume"
    if any(k in t for k in SUGGEST_TRIGGERS):
        return "suggest"
    if any(k in t for k in LIST_TRIGGERS):
        return "list"
    if any(k in t for k in ADD_TRIGGERS):
        return "add"
    return "general"

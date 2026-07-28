SUGGEST_TRIGGERS = [
    "what can i make", "what can i cook", "what should i", "suggest", "recipe",
    "what's for dinner", "whats for dinner", "ideas for dinner", "make with",
]
# Questions about the STORED recipe library (answered from recipes.db, not the
# LLM). Placed before cook/suggest/check so "do you have a recipe for X" queries
# the library instead of the pantry, while "let's make X" stays a cook.
RECIPE_QUERY_TRIGGERS = [
    "do you have a recipe", "do we have a recipe", "got a recipe",
    "is there a recipe", "do you know a recipe", "what recipes", "which recipes",
    "how many recipes", "recipe for",
]
LIST_TRIGGERS = [
    "what do i have", "what have i got", "what's in my", "whats in my",
    "what do i have left", "what's in stock", "whats in stock",
    "what's in the fridge", "whats in the fridge", "what's in the pantry",
    "whats in the pantry", "list my", "my inventory", "in my pantry",
    "what's in my pantry",
]
# Targeted "do we have X?" questions. These MUST be DB-grounded (inventory.check),
# never sent to the free LLM — otherwise the model invents inventory. "do i have"
# lives here (not LIST) so a specific-item question gets a yes/no, while the
# "what do i have" phrasings above still read back the whole pantry.
CHECK_TRIGGERS = [
    "do we have", "do i have", "do you have", "do we still have",
    "do i still have", "have we got", "have i got", "got any",
    "is there any", "are there any", "is there a", "are there",
]
COOK_TRIGGERS = [
    "let's make", "lets make", "let's cook", "lets cook", "walk me through",
    "guide me through", "how do i make", "how do you make", "how do i cook",
    "start the recipe", "start cooking", "help me make",
]
REMOVE_TRIGGERS = [
    "out of", "ran out", "run out", "used up", "used the last", "used all",
    "used the rest", "no more", "throw out", "threw out", "all gone",
    "remove ", "delete ",
]
ADD_TRIGGERS = [
    "bought", "grabbed", "picked up", "purchased", "just got", "stock up",
    " got ", "add ",
]


def classify(text: str) -> str:
    """Return 'volume', 'cook', 'recipe_query', 'suggest', 'list', 'check',
    'remove', 'add', or 'general'. Precedence:
    volume -> cook -> recipe_query -> suggest -> list -> check -> remove -> add
    -> general. (cook before recipe_query so "start the recipe for X" cooks while
    "do you have a recipe for X" queries the library;
    (cook before suggest so "let's make the omelette" starts a recipe while
    "what can I make" stays a browse; list before check so "what do I have"
    reads the whole pantry while "do I have milk" is a targeted lookup; check
    before add so "have we got X" / "got any X" isn't mistaken for a purchase;
    remove before add so "out of milk" isn't mistaken for a purchase.)"""
    t = " " + text.lower().strip() + " "
    if "volume" in t:
        return "volume"
    if any(k in t for k in COOK_TRIGGERS):
        return "cook"
    if any(k in t for k in RECIPE_QUERY_TRIGGERS):
        return "recipe_query"
    if any(k in t for k in SUGGEST_TRIGGERS):
        return "suggest"
    if any(k in t for k in LIST_TRIGGERS):
        return "list"
    if any(k in t for k in CHECK_TRIGGERS):
        return "check"
    if any(k in t for k in REMOVE_TRIGGERS):
        return "remove"
    if any(k in t for k in ADD_TRIGGERS):
        return "add"
    return "general"

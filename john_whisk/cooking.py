import re

from john_whisk import llm

# Lead-in phrases before the dish name in a "let's make X" utterance.
# Normalized (letters/digits/space only) so contractions match after the same
# normalization is applied to the speech. Longest matches win (see best_end).
_COOK_LEADINS = [
    "walk me through making", "walk me through", "guide me through making",
    "guide me through", "start the recipe for", "start the recipe",
    "start cooking", "how do i make", "how do you make", "how do i cook",
    "i want to make", "i d like to make", "help me make", "let s make",
    "lets make", "let s cook", "lets cook", "make the", "cook the",
]
_DISH_FILLERS = {"the", "a", "an", "some", "me", "for"}


def dish_from_text(text: str) -> str:
    """Pull the dish name out of a cook request, deterministically (no LLM)."""
    t = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    t = re.sub(r"\s+", " ", t).strip()
    best_end = -1
    for lead in _COOK_LEADINS:
        idx = t.find(lead)
        if idx != -1 and idx + len(lead) > best_end:
            best_end = idx + len(lead)
    tail = t[best_end:].strip() if best_end != -1 else t
    words = [w for w in tail.split() if w not in _DISH_FILLERS]
    return " ".join(words).strip()


# Navigation command families. Order matters: earlier lists win, so multiword
# "i m done" (stop) is matched before bare "done" (next).
_NAV = [
    ("stop", ["stop", "quit", "exit", "cancel", "never mind", "nevermind",
              "am done", "i m done", "im done", "all done", "done cooking",
              "that s all", "thats all", "forget it"]),
    ("restart", ["start over", "start again", "restart", "from the top",
                 "from the beginning", "beginning"]),
    ("back", ["go back", "back", "previous", "last step", "step before"]),
    ("repeat", ["repeat", "again", "say that again", "one more time",
                "what was that", "come again"]),
    ("ingredients", ["ingredient", "what do i need", "what do i use",
                     "shopping list"]),
    ("where", ["where am i", "where was i", "what step", "which step"]),
    ("next", ["next", "done", "continue", "go on", "keep going", "move on",
              "ready", "got it", "next step"]),
]


def classify_nav(text: str) -> str:
    """Map an in-recipe utterance to a navigation command, else 'unknown'."""
    t = " " + re.sub(r"[^a-z0-9\s]", " ", text.lower()) + " "
    t = re.sub(r"\s+", " ", t)
    for name, keys in _NAV:
        if any(k in t for k in keys):
            return name
    return "unknown"


class CookingSession:
    """Tracks position in an active recipe. Index -1 means the ingredients have
    been read but no step has started yet; 0..N-1 index into steps."""

    def __init__(self, title, ingredients, steps):
        self.title = title
        self.ingredients = ingredients
        self.steps = steps
        self.i = -1

    @property
    def started(self) -> bool:
        return self.i >= 0

    def current(self) -> str:
        return self.steps[self.i] if self.started else ""

    def advance(self) -> bool:
        """Move to the next step. Returns False if already on the last step."""
        if self.i < len(self.steps) - 1:
            self.i += 1
            return True
        return False

    def back(self) -> bool:
        """Move to the previous step. Returns False if on the first step."""
        if self.i > 0:
            self.i -= 1
            return True
        return False

    def restart(self):
        self.i = 0


def _say_step(session) -> str:
    return f"Step {session.i + 1} of {len(session.steps)}. {session.current()}"


def opening(session) -> str:
    intro = f"Okay, making {session.title}."
    if session.ingredients:
        intro += f" Here's what you'll need: {session.ingredients}."
    intro += " Say next when you're ready."
    return intro


def start(dish: str):
    """Generate a recipe and open a session. Returns (session, spoken reply),
    with session None if no recipe could be made."""
    recipe = llm.generate_recipe(dish)
    if not recipe:
        return None, "Sorry, I couldn't put a recipe together for that. Try another dish."
    session = CookingSession(recipe["title"], recipe["ingredients"], recipe["steps"])
    return session, opening(session)


def navigate(session, text):
    """Handle one in-recipe turn. Returns (spoken reply, session) where session
    is None once the recipe has ended."""
    nav = classify_nav(text)
    if nav == "stop":
        return "Okay, stopping the recipe.", None
    if nav == "next":
        if session.advance():
            return _say_step(session), session
        return f"That's the last step. Enjoy your {session.title}!", None
    if nav == "back":
        if session.back():
            return _say_step(session), session
        return "You're on the first step.", session
    if nav == "restart":
        session.restart()
        return _say_step(session), session
    if nav == "repeat":
        if session.started:
            return _say_step(session), session
        return opening(session), session
    if nav == "ingredients":
        if session.ingredients:
            return f"You'll need: {session.ingredients}.", session
        return "I don't have an ingredients list for this one.", session
    if nav == "where":
        if session.started:
            return f"You're on step {session.i + 1} of {len(session.steps)}.", session
        return "We haven't started the steps yet. Say next to begin.", session
    # unknown -> answer the question but stay in the recipe
    context = session.current() if session.started else session.ingredients
    return llm.ask_in_recipe(session.title, context, text), session

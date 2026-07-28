import re

from john_whisk import llm, inventory, recipes, restrictions

# Lead-in phrases before the dish name in a "let's make X" utterance.
# Normalized (letters/digits/space only) so contractions match after the same
# normalization is applied to the speech. Longest matches win (see best_end).
_COOK_LEADINS = [
    "walk me through making", "walk me through", "guide me through making",
    "guide me through", "start the recipe for", "start the recipe",
    "start cooking", "how do i make", "how do you make", "how do i cook",
    "i want to make", "i d like to make", "help me make", "let s make",
    "lets make", "let s cook", "lets cook", "also make", "also cook",
    "next make", "then make", "make the", "cook the",
    # planning phrasings (used by the grocery planner via dish_from_text)
    "i would like to make", "would like to make", "i m going to make",
    "im going to make", "going to make", "planning to make", "plan to make",
    "what do i need to make", "what do i need for", "add ingredients for",
    "shop for",
]
_DISH_FILLERS = {"the", "a", "an", "some", "me", "for"}

# Conservative phrases that, WHILE a recipe is active, mean "queue another
# recipe" (not a mid-recipe question). Deliberately excludes bare "how do i
# make ..." so "how do I make it fluffier" stays a question, not a new recipe.
_ENQUEUE_LEADINS = [
    "let s also make", "let s also cook", "also make", "also cook",
    "let s make", "lets make", "let s cook", "lets cook", "next make",
    "then make", "next let s make", "add a recipe", "queue up", "then cook",
]
# Explicit "clear the whole cooking session" phrases. Two-word "... all"
# variants + "everything" so plain "stop" / "all done" are NOT caught here.
_CANCEL_ALL = [
    "everything", "all the recipe", "stop all", "cancel all", "clear all",
    "forget all", "quit all", "all of them", "both recipes",
]
_RECIPES_QUERY = [
    "what am i making", "what am i cooking", "what are we making",
    "what are we cooking", "what recipes", "which recipes",
    "what am i working on",
]
# Phrases (WHILE cooking) that precede a missing ingredient the cook wants to
# swap. Longest-ending match wins (best_end) so the ingredient is what's left.
_SUBSTITUTION_LEADINS = [
    "what can i use instead of", "what can i use in place of",
    "what can i substitute for", "what do i use instead of", "instead of",
    "in place of", "a substitute for", "substitute for", "substitution for",
    "replacement for", "replace the", "sub for", "swap out the", "swap for",
    "i don t have any", "i don t have", "don t have any", "don t have",
    "dont have", "do not have", "i m out of", "im out of", "i am out of",
    "we re out of", "out of", "ran out of", "no more", "i have no",
]
_SUBSTITUTION_FILLERS = {"the", "a", "an", "any", "some", "my", "of", "more",
                         "left", "got"}


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
    """Open a session for a dish. Prefer a stored recipe (no LLM needed); fall
    back to LLM generation on a miss. Returns (session, spoken reply), with
    session None if no recipe could be made."""
    recipe = recipes.resolve(dish)
    if not recipe:
        return None, "Sorry, I couldn't put a recipe together for that. Try another dish."
    session = CookingSession(recipe["title"], recipe["ingredients"], recipe["steps"])
    reply = opening(session)
    warn = restrictions.warning(recipe)      # dietary heads-up (warn-and-proceed)
    return session, (warn + " " + reply if warn else reply)


def navigate(session, text):
    """Handle one in-recipe turn. Returns (spoken reply, session) where session
    is None once the recipe has ended."""
    nav = classify_nav(text)
    if nav == "stop":
        return f"Okay, stopping the {session.title}.", None
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


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", text.lower())).strip()


def next_up(session) -> str:
    """The hand-off line spoken when a queued recipe becomes current (waits for
    'next' before the first step, like a fresh recipe does)."""
    line = f"Next up is {session.title}."
    if session.ingredients:
        line += f" You'll need: {session.ingredients}."
    return line + " Say next when you're ready."


def is_recipes_query(text: str) -> bool:
    """True for "what recipes am I making right now" and kin (works anytime)."""
    return any(k in _normalize(text) for k in _RECIPES_QUERY)


def _is_cancel_all(text: str) -> bool:
    return any(k in _normalize(text) for k in _CANCEL_ALL)


def _is_cook_request(text: str) -> bool:
    return any(k in _normalize(text) for k in _ENQUEUE_LEADINS)


def _is_substitution(text: str) -> bool:
    return any(k in _normalize(text) for k in _SUBSTITUTION_LEADINS)


def parse_substitution_ingredient(text: str) -> str:
    """Pull the missing ingredient out of a substitution request,
    deterministically (no LLM). Strips the longest-ending lead-in, drops
    fillers; returns the ingredient (possibly multiword) or ""."""
    t = _normalize(text)
    best_end = -1
    for lead in _SUBSTITUTION_LEADINS:
        idx = t.find(lead)
        if idx != -1 and idx + len(lead) > best_end:
            best_end = idx + len(lead)
    tail = t[best_end:].strip() if best_end != -1 else t
    words = [w for w in tail.split() if w not in _SUBSTITUTION_FILLERS]
    return " ".join(words).strip()


def _join_names(names) -> str:
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return names[0] + " and " + names[1]
    return ", ".join(names[:-1]) + ", and " + names[-1]


class Kitchen:
    """Owns the active recipe plus a queue of dish names waiting their turn, so
    the cook works through one recipe at a time and then the next. Orchestrates
    the unchanged CookingSession / start / navigate mechanics."""

    def __init__(self):
        self.current = None      # active CookingSession, or None
        self.queue = []          # dish-name strings not yet started

    @property
    def active(self) -> bool:
        return self.current is not None

    def begin(self, dish: str) -> str:
        """Start `dish` now if idle, else queue it behind the current recipe."""
        if self.active:
            self.queue.append(dish)
            return f"Okay, I'll make {dish} after the {self.current.title}."
        session, reply = start(dish)
        self.current = session   # None if generation failed; reply explains
        return reply

    def _advance_queue(self, closing: str) -> str:
        """The current recipe just ended. Announce the next generatable queued
        recipe (waiting for 'next'), skipping any that fail; else go idle."""
        while self.queue:
            dish = self.queue.pop(0)
            session, _ = start(dish)
            if session:
                self.current = session
                return closing + " " + next_up(session)
            closing += f" I couldn't put together a recipe for {dish}, so I'll skip it."
        self.current = None
        return closing

    def navigate(self, text: str) -> str:
        """One in-recipe turn: cancel-all, enqueue-another, substitution, or step
        navigation (advancing the queue when the current recipe ends)."""
        if _is_cancel_all(text):
            return self.cancel_all()
        if _is_cook_request(text):
            return self.begin(dish_from_text(text))
        if _is_substitution(text):
            ingredient = parse_substitution_ingredient(text)
            if ingredient:
                # pantry-grounded swap; stays on the current step
                return inventory.substitute(self.current.title,
                                            self.current.current(), ingredient)
        reply, session = navigate(self.current, text)
        if session is None:
            return self._advance_queue(reply)
        self.current = session
        return reply

    def cancel_all(self) -> str:
        self.current = None
        self.queue = []
        return "Okay, I've cleared all the recipes."

    def summary(self) -> str:
        if not self.active:
            return "You're not making anything right now."
        s = f"You're making {self.current.title} right now"
        if self.queue:
            s += ", with " + _join_names(self.queue) + " up next"
        return s + "."

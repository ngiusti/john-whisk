from john_whisk import cooking
from john_whisk.cooking import Kitchen

OMELETTE = {"title": "omelette", "ingredients": "eggs, butter",
            "steps": ["Whisk the eggs.", "Melt the butter.", "Pour and cook."]}
TOAST = {"title": "toast", "ingredients": "bread, butter",
         "steps": ["Toast the bread.", "Butter it."]}


def _recipes(monkeypatch, mapping):
    monkeypatch.setattr(cooking.llm, "generate_recipe", lambda dish: mapping.get(dish))


# --- begin: start when idle, enqueue when busy ----------------------------

def test_begin_starts_when_idle(monkeypatch):
    _recipes(monkeypatch, {"omelette": OMELETTE})
    k = Kitchen()
    reply = k.begin("omelette")
    assert k.active and k.current.title == "omelette"
    assert "omelette" in reply.lower()


def test_begin_enqueues_when_busy(monkeypatch):
    _recipes(monkeypatch, {"omelette": OMELETTE, "toast": TOAST})
    k = Kitchen()
    k.begin("omelette")
    reply = k.begin("toast")
    assert k.current.title == "omelette"      # current unchanged
    assert k.queue == ["toast"]               # toast queued
    assert "toast" in reply.lower() and "after" in reply.lower()


# --- hand-off on finishing the last step ----------------------------------

def test_finish_hands_off_to_queued(monkeypatch):
    _recipes(monkeypatch, {"omelette": OMELETTE, "toast": TOAST})
    k = Kitchen()
    k.begin("omelette")
    k.begin("toast")
    k.navigate("next"); k.navigate("next"); k.navigate("next")   # steps 1-3
    reply = k.navigate("next")                                   # past last -> hand off
    assert k.current.title == "toast"
    assert not k.current.started        # announced, waiting for "next"
    assert "toast" in reply.lower() and "next" in reply.lower()


def test_stop_advances_to_queued(monkeypatch):
    _recipes(monkeypatch, {"omelette": OMELETTE, "toast": TOAST})
    k = Kitchen()
    k.begin("omelette")
    k.begin("toast")
    k.navigate("next")                  # step 1 of omelette
    reply = k.navigate("I'm done")      # stop current -> advance
    assert k.current.title == "toast"
    assert "toast" in reply.lower()


def test_stop_with_empty_queue_ends(monkeypatch):
    _recipes(monkeypatch, {"omelette": OMELETTE})
    k = Kitchen()
    k.begin("omelette")
    k.navigate("next")
    reply = k.navigate("stop")
    assert not k.active and k.current is None
    assert "stop" in reply.lower()


def test_finish_last_recipe_ends(monkeypatch):
    _recipes(monkeypatch, {"omelette": OMELETTE})
    k = Kitchen()
    k.begin("omelette")
    for _ in range(3):
        k.navigate("next")
    reply = k.navigate("next")          # past last, nothing queued
    assert not k.active
    assert "omelette" in reply.lower()


# --- enqueue while cooking (mid-recipe cook request) ----------------------

def test_cook_request_while_cooking_enqueues(monkeypatch):
    _recipes(monkeypatch, {"omelette": OMELETTE, "toast": TOAST})
    k = Kitchen()
    k.begin("omelette")
    k.navigate("next")
    reply = k.navigate("let's also make toast")
    assert k.current.title == "omelette"        # stayed on omelette
    assert k.queue == ["toast"]
    assert "toast" in reply.lower()


# --- cancel everything ----------------------------------------------------

def test_cancel_everything_clears_all(monkeypatch):
    _recipes(monkeypatch, {"omelette": OMELETTE, "toast": TOAST})
    k = Kitchen()
    k.begin("omelette")
    k.begin("toast")
    k.navigate("next")
    reply = k.navigate("cancel everything")
    assert not k.active and k.queue == []
    assert "cancel" in reply.lower() or "cleared" in reply.lower()


def test_plain_stop_is_not_cancel_all(monkeypatch):
    # "stop" alone must advance the queue, not clear it
    _recipes(monkeypatch, {"omelette": OMELETTE, "toast": TOAST})
    k = Kitchen()
    k.begin("omelette")
    k.begin("toast")
    k.navigate("next")
    k.navigate("stop")
    assert k.current.title == "toast"           # advanced, not cleared


# --- summary --------------------------------------------------------------

def test_summary_idle():
    assert "not making anything" in Kitchen().summary().lower()


def test_summary_single(monkeypatch):
    _recipes(monkeypatch, {"omelette": OMELETTE})
    k = Kitchen()
    k.begin("omelette")
    s = k.summary().lower()
    assert "omelette" in s and "toast" not in s


def test_summary_with_queue(monkeypatch):
    _recipes(monkeypatch, {"omelette": OMELETTE, "toast": TOAST})
    k = Kitchen()
    k.begin("omelette")
    k.begin("toast")
    s = k.summary().lower()
    assert "omelette" in s and "toast" in s


# --- generation failure for a queued dish is skipped ----------------------

def test_handoff_skips_failed_generation(monkeypatch):
    # toast fails to generate; the one after (eggs) should be reached
    eggs = {"title": "eggs", "ingredients": "eggs", "steps": ["Fry an egg.", "Season it."]}
    _recipes(monkeypatch, {"omelette": OMELETTE, "toast": None, "eggs": eggs})
    k = Kitchen()
    k.begin("omelette")
    k.queue = ["toast", "eggs"]
    k.navigate("next")
    reply = k.navigate("stop")
    assert k.current.title == "eggs"
    assert "toast" in reply.lower()             # mentions it couldn't make toast


# --- predicates -----------------------------------------------------------

def test_is_recipes_query_true():
    assert cooking.is_recipes_query("what recipes am I making right now")
    assert cooking.is_recipes_query("what am I cooking")


def test_is_recipes_query_false():
    assert not cooking.is_recipes_query("what can I make for dinner")
    assert not cooking.is_recipes_query("next")

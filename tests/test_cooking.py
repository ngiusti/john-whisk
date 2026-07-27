from john_whisk import cooking, router
from john_whisk.cooking import CookingSession

RECIPE = {
    "title": "omelette",
    "ingredients": "eggs, butter, salt",
    "steps": ["Whisk the eggs.", "Melt the butter.", "Pour and cook."],
}


def _session():
    return CookingSession(RECIPE["title"], RECIPE["ingredients"], RECIPE["steps"])


# --- nav classification ---------------------------------------------------

def test_nav_next():
    assert cooking.classify_nav("next") == "next"


def test_nav_done_is_next():
    assert cooking.classify_nav("done") == "next"


def test_nav_im_done_is_stop():
    assert cooking.classify_nav("I'm done") == "stop"


def test_nav_i_am_done_is_stop():
    # whisper often transcribes the uncontracted form; must still mean stop
    assert cooking.classify_nav("I am done") == "stop"


def test_nav_repeat():
    assert cooking.classify_nav("can you repeat that") == "repeat"


def test_nav_back():
    assert cooking.classify_nav("go back") == "back"


def test_nav_restart():
    assert cooking.classify_nav("let's start over") == "restart"


def test_nav_ingredients():
    assert cooking.classify_nav("what do I need") == "ingredients"


def test_nav_where():
    assert cooking.classify_nav("what step am I on") == "where"


def test_nav_unknown():
    assert cooking.classify_nav("how hot should the pan be") == "unknown"


# --- dish extraction ------------------------------------------------------

def test_dish_simple():
    assert cooking.dish_from_text("let's make an omelette") == "omelette"


def test_dish_multiword():
    assert cooking.dish_from_text("how do I make chicken alfredo") == "chicken alfredo"


def test_dish_walk_through():
    assert cooking.dish_from_text("walk me through making pancakes") == "pancakes"


def test_dish_recipe_for():
    assert cooking.dish_from_text("start the recipe for fried rice") == "fried rice"


# --- session navigation flows ---------------------------------------------

def test_advance_reads_first_step():
    s = _session()
    reply, out = cooking.navigate(s, "next")
    assert out is s
    assert "Step 1 of 3" in reply and "Whisk the eggs." in reply


def test_advance_through_to_end_ends_session():
    s = _session()
    cooking.navigate(s, "next")   # step 1
    cooking.navigate(s, "next")   # step 2
    cooking.navigate(s, "next")   # step 3 (last)
    reply, out = cooking.navigate(s, "next")   # past the end
    assert out is None
    assert "last step" in reply.lower() and "omelette" in reply


def test_back_at_first_step_holds():
    s = _session()
    cooking.navigate(s, "next")
    reply, out = cooking.navigate(s, "back")
    assert out is s and "first step" in reply.lower()


def test_back_moves_to_previous():
    s = _session()
    cooking.navigate(s, "next")
    cooking.navigate(s, "next")
    reply, out = cooking.navigate(s, "back")
    assert "Step 1 of 3" in reply


def test_repeat_before_start_reads_intro():
    s = _session()
    reply, out = cooking.navigate(s, "repeat")
    assert "you'll need" in reply.lower() and out is s


def test_restart_returns_to_first_step():
    s = _session()
    cooking.navigate(s, "next")
    cooking.navigate(s, "next")
    reply, out = cooking.navigate(s, "start over")
    assert "Step 1 of 3" in reply


def test_ingredients_query():
    s = _session()
    cooking.navigate(s, "next")
    reply, out = cooking.navigate(s, "what do I need")
    assert "eggs" in reply and out is s


def test_where_am_i():
    s = _session()
    cooking.navigate(s, "next")
    cooking.navigate(s, "next")
    reply, out = cooking.navigate(s, "where am I")
    assert "step 2 of 3" in reply.lower()


def test_stop_ends_session():
    s = _session()
    cooking.navigate(s, "next")
    reply, out = cooking.navigate(s, "I'm done")
    assert out is None and "stop" in reply.lower()


def test_unknown_falls_through_to_llm_and_stays(monkeypatch):
    s = _session()
    cooking.navigate(s, "next")
    monkeypatch.setattr(cooking.llm, "ask_in_recipe", lambda title, step, q: "Medium heat.")
    reply, out = cooking.navigate(s, "how hot should the pan be")
    assert reply == "Medium heat." and out is s


# --- start (recipe generation) --------------------------------------------

def test_start_success(monkeypatch):
    monkeypatch.setattr(cooking.llm, "generate_recipe", lambda dish: RECIPE)
    session, reply = cooking.start("omelette")
    assert session is not None
    assert "omelette" in reply.lower() and "you'll need" in reply.lower()


def test_start_failure(monkeypatch):
    monkeypatch.setattr(cooking.llm, "generate_recipe", lambda dish: None)
    session, reply = cooking.start("moon rocks")
    assert session is None and "couldn't" in reply.lower()


# --- router: the new "cook" intent ----------------------------------------

def test_router_cook_intent():
    assert router.classify("let's make an omelette") == "cook"


def test_router_how_do_i_make():
    assert router.classify("how do I make pancakes") == "cook"


def test_router_cook_does_not_shadow_suggest():
    assert router.classify("what can I make for dinner") == "suggest"


def test_router_cook_does_not_shadow_add():
    assert router.classify("I just bought pasta") == "add"

from john_whisk import config, recipes, router


def _fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RECIPES_DB_PATH", str(tmp_path / "r.db"))


# --- router: recipe_query intent, without shadowing cook/suggest/check ----

def test_router_do_you_have_recipe():
    assert router.classify("do you have a recipe for chicken alfredo") == "recipe_query"


def test_router_how_many_recipes():
    assert router.classify("how many recipes do you have") == "recipe_query"


def test_router_what_recipes():
    assert router.classify("what recipes do you have") == "recipe_query"


def test_router_lets_make_still_cook():
    assert router.classify("let's make chicken alfredo") == "cook"


def test_router_what_can_i_make_still_suggest():
    assert router.classify("what can I make for dinner") == "suggest"


def test_router_pantry_check_not_shadowed():
    assert router.classify("do we have milk") == "check"


# --- answer_query responder -----------------------------------------------

def test_answer_how_many(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    recipes.add_recipe("Chicken Alfredo", "chicken", ["Cook."])
    assert "1" in recipes.answer_query("how many recipes do you have")


def test_answer_have_recipe_yes(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    recipes.add_recipe("Chicken Alfredo", "chicken, pasta", ["Cook."])
    reply = recipes.answer_query("do you have a recipe for chicken alfredo").lower()
    assert reply.startswith("yes") and "chicken alfredo" in reply


def test_answer_have_recipe_no(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    recipes.add_recipe("Chicken Alfredo", "chicken", ["Cook."])
    reply = recipes.answer_query("do you have a recipe for sushi").lower()
    assert reply.startswith("no") and "sushi" in reply


def test_answer_what_recipes_lists(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    recipes.add_recipe("Chicken Alfredo", "chicken", ["Cook."])
    recipes.add_recipe("Fluffy Pancakes", "flour", ["Mix."])
    reply = recipes.answer_query("what recipes do you have")
    assert "2" in reply and ("Alfredo" in reply or "Pancakes" in reply)


def test_answer_empty_store(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    assert "don't have any" in recipes.answer_query("what recipes do you have").lower()

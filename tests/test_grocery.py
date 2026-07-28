from john_whisk import config, db, grocery, recipes, router, llm


def _fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "p.db"))
    monkeypatch.setattr(config, "RECIPES_DB_PATH", str(tmp_path / "r.db"))


# --- grocery store --------------------------------------------------------

def test_add_and_items(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    grocery.add(["milk", "eggs"])
    assert set(grocery.items()) == {"milk", "eggs"}


def test_add_dedupes(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    grocery.add(["milk"])
    grocery.add(["Milk"])
    assert len(grocery.items()) == 1


def test_add_string(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    grocery.add("butter")
    assert grocery.items() == ["butter"]


def test_remove(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    grocery.add(["milk", "eggs"])
    grocery.remove(["milk"])
    assert grocery.items() == ["eggs"]


def test_clear(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    grocery.add(["milk", "eggs"])
    grocery.clear()
    assert grocery.items() == []


def test_add_from_text(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    grocery.add_from_text("add milk to my grocery list")
    assert "milk" in grocery.items()


def test_answer_list_empty(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    assert "empty" in grocery.answer_list().lower()


def test_answer_list_has_items(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    grocery.add(["milk", "eggs"])
    r = grocery.answer_list().lower()
    assert "milk" in r and "eggs" in r


# --- missing-ingredient detection ----------------------------------------

def test_missing_excludes_staples_and_covers_pantry():
    pantry = [{"name": "chicken"}]
    m = grocery._missing("2 chicken breasts, 1 teaspoon salt, 1 cup heavy cream", pantry)
    assert m == ["1 cup heavy cream"]            # chicken covered, salt staple, cream missing


def test_missing_plural_tolerant():
    m = grocery._missing("2 eggs, 1 cup flour", [{"name": "egg"}])
    assert m == ["1 cup flour"]                  # egg covers eggs


def test_missing_have_everything():
    assert grocery._missing("chicken, cream", [{"name": "chicken"}, {"name": "cream"}]) == []


# --- recipes.resolve ------------------------------------------------------

def test_resolve_prefers_stored(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    recipes.add_recipe("Chicken Alfredo", "chicken, cream", ["Cook."])
    monkeypatch.setattr(llm, "generate_recipe",
                        lambda d: (_ for _ in ()).throw(AssertionError("no LLM")))
    assert recipes.resolve("chicken alfredo")["title"] == "Chicken Alfredo"


def test_resolve_llm_fallback(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    monkeypatch.setattr(llm, "generate_recipe",
                        lambda d: {"title": "x", "ingredients": "y", "steps": ["z"]})
    assert recipes.resolve("nope")["title"] == "x"


# --- plan_meal ------------------------------------------------------------

def test_plan_meal_adds_missing(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    monkeypatch.setattr(recipes, "resolve", lambda d: {
        "title": "Chicken Alfredo", "ingredients": "chicken, cream, parmesan", "steps": ["x"]})
    db.add_items([{"name": "chicken", "quantity": None, "unit": None}])
    reply = grocery.plan_meal("chicken alfredo")
    assert reply.lower().startswith("adding missing ingredients")
    assert "cream" in reply and "parmesan" in reply
    assert set(grocery.items()) == {"cream", "parmesan"}


def test_plan_meal_have_everything(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    monkeypatch.setattr(recipes, "resolve",
                        lambda d: {"title": "Toast", "ingredients": "bread, butter", "steps": ["x"]})
    db.add_items([{"name": "bread", "quantity": None, "unit": None},
                  {"name": "butter", "quantity": None, "unit": None}])
    assert "everything" in grocery.plan_meal("toast").lower()
    assert grocery.items() == []


def test_plan_meal_no_recipe(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    monkeypatch.setattr(recipes, "resolve", lambda d: None)
    assert "don't have a recipe" in grocery.plan_meal("moon rocks").lower()


# --- router ---------------------------------------------------------------

def test_router_plan_would_like():
    assert router.classify("I would like to make chicken alfredo") == "plan"


def test_router_plan_want_to_make():
    assert router.classify("I want to make lasagne") == "plan"


def test_router_lets_make_still_cook():
    assert router.classify("let's make chicken alfredo") == "cook"


def test_router_grocery_list_query():
    assert router.classify("what's on my grocery list") == "grocery"


def test_router_add_to_grocery_not_pantry():
    assert router.classify("add milk to my grocery list") == "grocery"


def test_router_remove_from_grocery_not_pantry():
    assert router.classify("remove eggs from my grocery list") == "grocery"


def test_router_bought_still_add():
    assert router.classify("I bought milk") == "add"

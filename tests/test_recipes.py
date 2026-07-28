from john_whisk import config, recipes

ALFREDO = ("Chicken Alfredo", "chicken, pasta, cream, parmesan",
           ["Cook the pasta.", "Make the sauce.", "Combine."])
PANCAKES = ("Fluffy Pancakes", "flour, milk, eggs",
            ["Mix batter.", "Cook on a griddle."])


def _fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RECIPES_DB_PATH", str(tmp_path / "r.db"))


def test_add_and_count(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    assert recipes.add_recipe(*ALFREDO) is True
    assert recipes.add_recipe(*PANCAKES) is True
    assert recipes.count() == 2


def test_add_dedupes_by_title(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    recipes.add_recipe(*ALFREDO)
    assert recipes.add_recipe("chicken alfredo", "x", ["y"]) is False  # dup by norm title
    assert recipes.count() == 1


def test_find_exact(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    recipes.add_recipe(*ALFREDO)
    r = recipes.find("chicken alfredo")
    assert r is not None and r["title"] == "Chicken Alfredo"


def test_find_fuzzy(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    recipes.add_recipe(*ALFREDO)
    recipes.add_recipe(*PANCAKES)
    assert recipes.find("alfredo")["title"] == "Chicken Alfredo"
    assert recipes.find("pancakes")["title"] == "Fluffy Pancakes"


def test_find_no_match_returns_none(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    recipes.add_recipe(*ALFREDO)
    assert recipes.find("pizza") is None
    assert recipes.find("chicken soup") is None       # only 1 word overlap, not enough


def test_find_returns_steps_as_list(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    recipes.add_recipe(*ALFREDO)
    r = recipes.find("chicken alfredo")
    assert r["steps"] == ["Cook the pasta.", "Make the sauce.", "Combine."]
    assert r["ingredients"] == "chicken, pasta, cream, parmesan"


def test_add_accepts_list_ingredients(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    recipes.add_recipe("Toast", ["bread", "butter"], ["Toast it."])
    assert recipes.find("toast")["ingredients"] == "bread, butter"


def test_search_ranked(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    recipes.add_recipe(*ALFREDO)
    recipes.add_recipe("Chicken Soup", "chicken, broth", ["Simmer."])
    hits = recipes.search("chicken", limit=5)
    assert len(hits) == 2
    assert all("chicken" in h["title"].lower() for h in hits)


def test_count_empty(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    assert recipes.count() == 0


# --- cooking integration: prefer stored, fall back to LLM ------------------

def test_cooking_start_prefers_stored(tmp_path, monkeypatch):
    from john_whisk import cooking, llm
    _fresh(tmp_path, monkeypatch)
    recipes.add_recipe(*ALFREDO)
    called = {"llm": False}
    monkeypatch.setattr(llm, "generate_recipe",
                        lambda d: called.__setitem__("llm", True) or None)
    session, reply = cooking.start("chicken alfredo")
    assert session is not None
    assert session.title == "Chicken Alfredo"
    assert session.steps == ["Cook the pasta.", "Make the sauce.", "Combine."]
    assert called["llm"] is False              # stored hit -> LLM never called


def test_cooking_start_falls_back_to_llm(tmp_path, monkeypatch):
    from john_whisk import cooking, llm
    _fresh(tmp_path, monkeypatch)
    monkeypatch.setattr(llm, "generate_recipe",
                        lambda d: {"title": "pizza", "ingredients": "dough",
                                   "steps": ["Bake.", "Slice."]})
    session, reply = cooking.start("pizza")
    assert session is not None and session.title == "pizza"

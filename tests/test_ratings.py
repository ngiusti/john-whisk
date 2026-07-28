from john_whisk import config, ratings, router


def _fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "p.db"))


# --- store ----------------------------------------------------------------

def test_cooked_and_last(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    ratings.cooked("Chicken Alfredo")
    ratings.cooked("Tacos")
    assert ratings.last_cooked() == "Tacos"


def test_rate_favorites_and_disliked(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    ratings.rate("Tacos", True)
    ratings.rate("Sushi", False)
    assert ratings.favorites() == ["Tacos"]
    assert ratings.disliked() == ["Sushi"]


def test_rate_upsert(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    ratings.rate("Tacos", True)
    ratings.rate("Tacos", False)
    assert ratings.favorites() == []
    assert ratings.disliked() == ["Tacos"]


# --- rate_from_text -------------------------------------------------------

def test_rate_implicit_up(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    ratings.cooked("Chicken Alfredo")
    assert ratings.rate_from_text("that was great") == ("Chicken Alfredo", 1)
    assert ratings.favorites() == ["Chicken Alfredo"]


def test_rate_explicit_down(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    target, s = ratings.rate_from_text("I don't like sushi")
    assert target.lower() == "sushi" and s == -1


def test_rate_dont_suggest_targets_last(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    ratings.cooked("Liver Stew")
    assert ratings.rate_from_text("don't suggest that again") == ("Liver Stew", -1)


def test_rate_negative_beats_embedded_like(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    ratings.cooked("X")
    assert ratings.rate_from_text("I didn't like that")[1] == -1


def test_rate_unclear_returns_none(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    assert ratings.rate_from_text("what time is it") is None


# --- preference clause + favorites ----------------------------------------

def test_preference_clause(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    ratings.rate("Sushi", False)
    ratings.rate("Tacos", True)
    c = ratings.preference_clause().lower()
    assert "sushi" in c and "tacos" in c


def test_preference_clause_empty(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    assert ratings.preference_clause() == ""


def test_answer_favorites(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    ratings.rate("Tacos", True)
    assert "tacos" in ratings.answer_favorites().lower()


def test_answer_favorites_empty(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    assert "haven't rated" in ratings.answer_favorites().lower()


# --- router ---------------------------------------------------------------

def test_router_that_was_great():
    assert router.classify("that was great") == "rate"


def test_router_i_love():
    assert router.classify("I love tacos") == "rate"


def test_router_dont_suggest():
    assert router.classify("don't suggest that again") == "rate"


def test_router_favorites():
    assert router.classify("what are my favorite recipes") == "rate"


def test_router_lets_make_still_cook():
    assert router.classify("let's make tacos") == "cook"


def test_router_would_like_still_plan():
    assert router.classify("I would like to make tacos") == "plan"


# --- integration ----------------------------------------------------------

def test_cooking_start_records_cooked(tmp_path, monkeypatch):
    from john_whisk import cooking, recipes as rec
    _fresh(tmp_path, monkeypatch)
    monkeypatch.setattr(rec, "resolve", lambda d: {"title": "Tacos", "ingredients": "x", "steps": ["y"]})
    cooking.start("tacos")
    assert ratings.last_cooked() == "Tacos"


def test_suggest_includes_preferences(tmp_path, monkeypatch):
    from john_whisk import inventory, db, llm
    _fresh(tmp_path, monkeypatch)
    db.add_items([{"name": "eggs", "quantity": None, "unit": None}])
    ratings.rate("Sushi", False)
    captured = {}

    def fake(pantry, request):
        captured["req"] = request
        return "ok"

    monkeypatch.setattr(llm, "suggest_recipe", fake)
    inventory.suggest("what can I make")
    assert "sushi" in captured["req"].lower()

from john_whisk import config, restrictions, router


def _fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "p.db"))


# --- store + normalization ------------------------------------------------

def test_add_and_active(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    restrictions.add(["nuts"])
    assert restrictions.active() == ["nuts"]


def test_add_dedupes(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    restrictions.add(["nuts"])
    restrictions.add(["nuts"])
    assert restrictions.active() == ["nuts"]


def test_remove(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    restrictions.add(["nuts", "dairy"])
    restrictions.remove(["nuts"])
    assert restrictions.active() == ["dairy"]


def test_clear(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    restrictions.add(["nuts", "dairy"])
    restrictions.clear()
    assert restrictions.active() == []


def test_canonical_phrasings():
    assert restrictions._canonical("allergic to nuts") == "nuts"
    assert restrictions._canonical("i'm gluten free") == "gluten"
    assert restrictions._canonical("no dairy") == "dairy"
    assert restrictions._canonical("i'm vegetarian") == "vegetarian"
    assert restrictions._canonical("vegan") == "vegan"


def test_canonical_unknown():
    assert restrictions._canonical("blue food") is None


def test_set_from_text(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    restrictions.set_from_text("I'm allergic to nuts")
    assert "nuts" in restrictions.active()


# --- detection (check) ----------------------------------------------------

def test_check_dairy_flags_with_subs(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    restrictions.add(["dairy"])
    v = restrictions.check("2 chicken breasts, 1 cup heavy cream, half cup parmesan")
    flagged = {x["ingredient"]: x["sub"] for x in v}
    assert "1 cup heavy cream" in flagged and "half cup parmesan" in flagged
    assert flagged["1 cup heavy cream"] == "soy cream"
    assert "2 chicken breasts" not in flagged           # chicken is not dairy


def test_check_vegetarian_flags_meat(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    restrictions.add(["vegetarian"])
    v = restrictions.check("2 chicken breasts, 1 cup rice")
    assert any(x["keyword"] == "chicken" and x["sub"] == "tofu" for x in v)


def test_check_no_false_positive_whole_word(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    restrictions.add(["nuts"])
    assert restrictions.check("2 tablespoons butter, salt") == []   # butter != nut


def test_check_inactive_ignored(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    assert restrictions.check("1 cup heavy cream") == []            # nothing active


def test_check_sub_avoids_other_restriction(tmp_path, monkeypatch):
    # dairy + nuts active: milk's usual sub 'almond milk' would violate nuts,
    # so it must NOT suggest an almond-based substitute
    _fresh(tmp_path, monkeypatch)
    restrictions.add(["dairy", "nuts"])
    v = restrictions.check("1 cup milk")
    sub = next(x["sub"] for x in v if x["keyword"] == "milk")
    assert sub is None or "almond" not in (sub or "")


# --- warning message ------------------------------------------------------

def test_warning_includes_subs_and_caution(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    restrictions.add(["dairy"])
    w = restrictions.warning({"title": "Chicken Alfredo",
                              "ingredients": "chicken, 1 cup heavy cream"})
    assert "dairy" in w.lower()
    assert "soy cream" in w
    assert "label" in w.lower()                         # safety caution


def test_warning_empty_when_clean(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    restrictions.add(["dairy"])
    assert restrictions.warning({"title": "Salad", "ingredients": "lettuce, tomato"}) == ""


def test_answer_list(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    restrictions.add(["nuts", "dairy"])
    r = restrictions.answer_list().lower()
    assert "nuts" in r and "dairy" in r


def test_answer_list_empty(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    assert "haven't set" in restrictions.answer_list().lower()


# --- router ---------------------------------------------------------------

def test_router_allergic():
    assert router.classify("I'm allergic to nuts") == "dietary"


def test_router_vegetarian():
    assert router.classify("I'm vegetarian") == "dietary"


def test_router_my_restrictions():
    assert router.classify("what are my restrictions") == "dietary"


def test_router_bought_still_add():
    assert router.classify("I bought milk") == "add"


# --- integration ----------------------------------------------------------

def test_cooking_start_warns_when_violating(tmp_path, monkeypatch):
    from john_whisk import cooking, recipes as rec
    _fresh(tmp_path, monkeypatch)
    restrictions.add(["dairy"])
    monkeypatch.setattr(rec, "resolve", lambda d: {
        "title": "Alfredo", "ingredients": "chicken, 1 cup heavy cream", "steps": ["Cook."]})
    session, reply = cooking.start("alfredo")
    assert session is not None
    assert "dairy" in reply.lower() and "soy cream" in reply


def test_cooking_start_no_warn_when_clean(tmp_path, monkeypatch):
    from john_whisk import cooking, recipes as rec
    _fresh(tmp_path, monkeypatch)
    restrictions.add(["dairy"])
    monkeypatch.setattr(rec, "resolve", lambda d: {
        "title": "Salad", "ingredients": "lettuce, tomato", "steps": ["Toss."]})
    _, reply = cooking.start("salad")
    assert "heads up" not in reply.lower()


def test_plan_meal_warns(tmp_path, monkeypatch):
    from john_whisk import grocery, recipes as rec
    _fresh(tmp_path, monkeypatch)
    restrictions.add(["dairy"])
    monkeypatch.setattr(rec, "resolve", lambda d: {
        "title": "Alfredo", "ingredients": "chicken, 1 cup heavy cream", "steps": ["x"]})
    assert "dairy" in grocery.plan_meal("alfredo").lower()


def test_suggest_includes_restrictions(tmp_path, monkeypatch):
    from john_whisk import inventory, db, llm
    _fresh(tmp_path, monkeypatch)
    db.add_items([{"name": "eggs", "quantity": None, "unit": None}])
    restrictions.add(["vegetarian"])
    captured = {}

    def fake_suggest(pantry, request):
        captured["req"] = request
        return "ok"

    monkeypatch.setattr(llm, "suggest_recipe", fake_suggest)
    inventory.suggest("what can I make")
    assert "vegetarian" in captured["req"].lower()

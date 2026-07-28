from john_whisk import config, equipment, router


def _fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "p.db"))


# --- store ----------------------------------------------------------------

def test_add_owned(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    equipment.add(["blender"])
    assert equipment.owned() == ["blender"]


def test_add_dedupes(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    equipment.add(["blender"])
    equipment.add(["blender"])
    assert equipment.owned() == ["blender"]


def test_remove(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    equipment.add(["blender", "oven"])
    equipment.remove(["blender"])
    assert equipment.owned() == ["oven"]


def test_clear(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    equipment.add(["blender"])
    equipment.clear()
    assert equipment.owned() == []


def test_canonical():
    assert equipment._canonical("a blender") == "blender"
    assert equipment._canonical("crock pot") == "slow cooker"
    assert equipment._canonical("instant pot") == "pressure cooker"
    assert equipment._canonical("banana") is None


def test_set_from_text_multiple(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    equipment.set_from_text("I have a blender and a slow cooker")
    assert set(equipment.owned()) == {"blender", "slow cooker"}


# --- required / missing / warning -----------------------------------------

def test_required_blender():
    assert "blender" in equipment.required({"steps": ["Blend until smooth."]})


def test_required_oven():
    assert "oven" in equipment.required({"steps": ["Bake for 20 minutes."]})


def test_required_none_for_basics():
    assert equipment.required({"steps": ["Fry in a pan.", "Stir with a spoon."]}) == set()


def test_missing_when_not_owned(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    assert "blender" in equipment.missing({"steps": ["Blend until smooth."]})


def test_missing_when_owned(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    equipment.add(["blender"])
    assert equipment.missing({"steps": ["Blend until smooth."]}) == []


def test_warning(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    w = equipment.warning({"title": "Smoothie", "steps": ["Blend until smooth."]})
    assert "blender" in w.lower() and "equipment" in w.lower()


def test_warning_empty_when_owned(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    equipment.add(["blender"])
    assert equipment.warning({"title": "Smoothie", "steps": ["Blend."]}) == ""


# --- prompt clause + list -------------------------------------------------

def test_prompt_clause(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    equipment.add(["blender"])
    assert "blender" in equipment.prompt_clause().lower()


def test_prompt_clause_empty(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    assert equipment.prompt_clause() == ""


def test_answer_list(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    equipment.add(["blender", "oven"])
    r = equipment.answer_list().lower()
    assert "blender" in r and "oven" in r


def test_answer_list_empty(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    assert "haven't listed" in equipment.answer_list().lower()


# --- router ---------------------------------------------------------------

def test_router_i_have_blender():
    assert router.classify("I have a blender") == "equipment"


def test_router_what_equipment():
    assert router.classify("what equipment do I have") == "equipment"


def test_router_dont_have():
    assert router.classify("I don't have a blender") == "equipment"


def test_router_lets_make_still_cook():
    assert router.classify("let's make grilled cheese") == "cook"


def test_router_bought_still_add():
    assert router.classify("I bought milk") == "add"


# --- integration ----------------------------------------------------------

def test_cooking_start_warns_missing_equipment(tmp_path, monkeypatch):
    from john_whisk import cooking, recipes as rec
    _fresh(tmp_path, monkeypatch)
    monkeypatch.setattr(rec, "resolve", lambda d: {
        "title": "Smoothie", "ingredients": "banana", "steps": ["Blend until smooth."]})
    _, reply = cooking.start("smoothie")
    assert "blender" in reply.lower()


def test_suggest_includes_equipment(tmp_path, monkeypatch):
    from john_whisk import inventory, db, llm
    _fresh(tmp_path, monkeypatch)
    db.add_items([{"name": "eggs", "quantity": None, "unit": None}])
    equipment.add(["air fryer"])
    captured = {}

    def fake(pantry, request):
        captured["req"] = request
        return "ok"

    monkeypatch.setattr(llm, "suggest_recipe", fake)
    inventory.suggest("what can I make")
    assert "air fryer" in captured["req"].lower()

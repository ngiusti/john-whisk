from john_whisk import config, flavor, router, llm


def _fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "p.db"))


class _Resp:
    def __init__(self, t):
        self._t = t

    def raise_for_status(self):
        pass

    def json(self):
        return {"response": self._t}


# --- preference store -----------------------------------------------------

def test_add_prefs(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    flavor.add(["mild"])
    assert flavor.prefs() == ["mild"]


def test_add_dedupes(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    flavor.add(["mild"])
    flavor.add(["mild"])
    assert flavor.prefs() == ["mild"]


def test_clear(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    flavor.add(["mild"])
    flavor.clear()
    assert flavor.prefs() == []


# --- is_adjust ------------------------------------------------------------

def test_is_adjust_tone_down():
    assert flavor.is_adjust("tone down the spice")


def test_is_adjust_bolder():
    assert flavor.is_adjust("make it bolder")


def test_is_adjust_too_salty():
    assert flavor.is_adjust("this is too salty")


def test_not_adjust_next():
    assert not flavor.is_adjust("next")


def test_not_adjust_pan_question():
    assert not flavor.is_adjust("how hot should the pan be")


# --- llm.flavor_advice + tip ----------------------------------------------

def test_flavor_advice_prompt(monkeypatch):
    captured = {}

    def fake(url, json=None, timeout=None):
        captured["p"] = json
        return _Resp("Add lime.")

    monkeypatch.setattr(llm.requests, "post", fake)
    out = llm.flavor_advice("Chili", "Simmer the chili.", "tone down the spice", "mild")
    assert out == "Add lime."
    p = captured["p"]["prompt"]
    assert "Chili" in p and "tone down the spice" in p and "mild" in p


def test_tip_uses_prefs(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    flavor.add(["mild"])
    captured = {}

    def fake(title, step, req, prefs):
        captured["prefs"] = prefs
        return "tip"

    monkeypatch.setattr(llm, "flavor_advice", fake)
    flavor.tip("Chili", "step", "tone down")
    assert "mild" in captured["prefs"]


# --- preference parsing ---------------------------------------------------

def test_set_from_text_mild(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    flavor.set_from_text("we like it mild")
    assert "mild" in flavor.prefs()


def test_set_from_text_negated(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    flavor.set_from_text("we don't like it too spicy")
    assert any("spicy" in p for p in flavor.prefs())


def test_prompt_clause(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    flavor.add(["mild"])
    assert "mild" in flavor.prompt_clause().lower()


def test_prompt_clause_empty(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    assert flavor.prompt_clause() == ""


# --- router ---------------------------------------------------------------

def test_router_we_like_mild():
    assert router.classify("we like it mild") == "flavor"


def test_router_flavor_pref():
    assert router.classify("what are our flavor preferences") == "flavor"


def test_router_lets_make_still_cook():
    assert router.classify("let's make chili") == "cook"


# --- integration ----------------------------------------------------------

def test_navigate_flavor_tip(tmp_path, monkeypatch):
    from john_whisk import cooking
    from john_whisk.cooking import Kitchen
    _fresh(tmp_path, monkeypatch)
    monkeypatch.setattr(cooking.llm, "generate_recipe",
                        lambda d: {"title": "Chili", "ingredients": "beans",
                                   "steps": ["Simmer the chili.", "Serve."]})
    monkeypatch.setattr(cooking.flavor, "tip", lambda title, step, req: "Add lime.")
    k = Kitchen()
    k.begin("chili")
    k.navigate("next")
    reply = k.navigate("tone down the spice")
    assert reply == "Add lime." and k.current.title == "Chili"


def test_navigate_normal_question_still_asks(tmp_path, monkeypatch):
    from john_whisk import cooking
    from john_whisk.cooking import Kitchen
    _fresh(tmp_path, monkeypatch)
    monkeypatch.setattr(cooking.llm, "generate_recipe",
                        lambda d: {"title": "Chili", "ingredients": "beans",
                                   "steps": ["Simmer.", "Serve."]})
    monkeypatch.setattr(cooking.llm, "ask_in_recipe", lambda t, s, q: "Medium heat.")
    k = Kitchen()
    k.begin("chili")
    k.navigate("next")
    assert k.navigate("how hot should the pan be") == "Medium heat."


def test_suggest_includes_flavor(tmp_path, monkeypatch):
    from john_whisk import inventory, db
    _fresh(tmp_path, monkeypatch)
    db.add_items([{"name": "eggs", "quantity": None, "unit": None}])
    flavor.add(["bold"])
    captured = {}
    monkeypatch.setattr(llm, "suggest_recipe",
                        lambda p, r: captured.setdefault("req", r) or "ok")
    inventory.suggest("what can I make")
    assert "bold" in captured["req"].lower()

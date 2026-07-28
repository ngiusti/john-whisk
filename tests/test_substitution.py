from john_whisk import cooking, config, db, inventory, llm
from john_whisk.cooking import Kitchen


class _Resp:
    def __init__(self, t):
        self._t = t

    def raise_for_status(self):
        pass

    def json(self):
        return {"response": self._t}


# --- detection ------------------------------------------------------------

def test_is_substitution_dont_have():
    assert cooking._is_substitution("I don't have pine nuts")


def test_is_substitution_instead_of():
    assert cooking._is_substitution("what can I use instead of butter")


def test_is_substitution_out_of():
    assert cooking._is_substitution("I'm out of eggs")


def test_is_substitution_substitute_for():
    assert cooking._is_substitution("substitute for buttermilk")


def test_not_substitution_next():
    assert not cooking._is_substitution("next")


def test_not_substitution_question():
    assert not cooking._is_substitution("how hot should the pan be")


# --- ingredient parsing ---------------------------------------------------

def test_parse_instead_of():
    assert cooking.parse_substitution_ingredient("what can I use instead of pine nuts") == "pine nuts"


def test_parse_dont_have_any():
    assert cooking.parse_substitution_ingredient("I don't have any butter") == "butter"


def test_parse_out_of():
    assert cooking.parse_substitution_ingredient("I'm out of eggs") == "eggs"


def test_parse_substitute_for():
    assert cooking.parse_substitution_ingredient("substitute for buttermilk") == "buttermilk"


# --- llm.suggest_substitution --------------------------------------------

def test_suggest_substitution_prompt(monkeypatch):
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["p"] = json
        return _Resp("Use walnuts instead.")

    monkeypatch.setattr(llm.requests, "post", fake_post)
    out = llm.suggest_substitution("walnuts, olive oil", "pesto", "Toast the pine nuts.", "pine nuts")
    assert out == "Use walnuts instead."
    prompt = captured["p"]["prompt"]
    assert "pesto" in prompt and "pine nuts" in prompt and "walnuts, olive oil" in prompt
    assert "Toast the pine nuts." in prompt


def test_suggest_substitution_failure(monkeypatch):
    def boom(*a, **k):
        raise llm.requests.RequestException("down")

    monkeypatch.setattr(llm.requests, "post", boom)
    assert llm.suggest_substitution("eggs", "cake", "Mix.", "butter") == ""


# --- inventory.substitute -------------------------------------------------

def test_inventory_substitute_passes_pantry(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    db.add_items([{"name": "walnuts", "quantity": None, "unit": None}])
    captured = {}

    def fake_sub(pantry, title, step, ing):
        captured["pantry"] = pantry
        return "Use walnuts."

    monkeypatch.setattr(llm, "suggest_substitution", fake_sub)
    out = inventory.substitute("pesto", "Toast the pine nuts.", "pine nuts")
    assert out == "Use walnuts."
    assert "walnuts" in captured["pantry"]


def test_inventory_substitute_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(llm, "suggest_substitution", lambda *a, **k: "")
    assert "substitute" in inventory.substitute("cake", "Mix.", "butter").lower()


# --- Kitchen.navigate routing --------------------------------------------

RECIPE = {"title": "pesto", "ingredients": "basil, pine nuts",
          "steps": ["Toast the pine nuts.", "Blend everything."]}


def _kitchen(monkeypatch):
    monkeypatch.setattr(cooking.llm, "generate_recipe", lambda dish: RECIPE)
    k = Kitchen()
    k.begin("pesto")
    k.navigate("next")   # on step 1
    return k


def test_navigate_substitution_routes_and_stays(monkeypatch):
    k = _kitchen(monkeypatch)
    monkeypatch.setattr(cooking.inventory, "substitute",
                        lambda title, step, ing: f"Use walnuts instead of {ing}.")
    reply = k.navigate("I don't have pine nuts")
    assert reply == "Use walnuts instead of pine nuts."
    assert k.current.title == "pesto"          # stayed in the recipe
    assert k.current.started


def test_navigate_normal_question_still_asks(monkeypatch):
    k = _kitchen(monkeypatch)
    monkeypatch.setattr(cooking.llm, "ask_in_recipe", lambda t, s, q: "Medium heat.")
    assert k.navigate("how hot should the pan be") == "Medium heat."


def test_navigate_next_still_steps(monkeypatch):
    k = _kitchen(monkeypatch)
    reply = k.navigate("next")
    assert "Step 2 of 2" in reply

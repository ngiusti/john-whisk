from john_whisk import llm


class _Resp:
    def __init__(self, text):
        self._text = text

    def raise_for_status(self):
        pass

    def json(self):
        return {"response": self._text}


def _patch_ollama(monkeypatch, text):
    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: _Resp(text))


# --- generate_recipe: parsing the model's INGREDIENTS/STEPS format ---------

def test_generate_recipe_parses(monkeypatch):
    _patch_ollama(
        monkeypatch,
        "INGREDIENTS: eggs, butter, salt\n"
        "STEPS:\n"
        "1. Whisk three eggs in a bowl.\n"
        "2. Melt butter in a pan.\n"
        "3. Pour in the eggs and cook.\n",
    )
    r = llm.generate_recipe("omelette")
    assert r["title"] == "omelette"
    assert r["ingredients"] == "eggs, butter, salt"
    assert r["steps"] == [
        "Whisk three eggs in a bowl.",
        "Melt butter in a pan.",
        "Pour in the eggs and cook.",
    ]


def test_generate_recipe_too_few_steps(monkeypatch):
    _patch_ollama(monkeypatch, "INGREDIENTS: water\nSTEPS:\n1. Boil the water.\n")
    assert llm.generate_recipe("boiled water") is None


def test_generate_recipe_malformed(monkeypatch):
    _patch_ollama(monkeypatch, "I'm not sure how to make that, sorry.")
    assert llm.generate_recipe("moon rocks") is None


def test_generate_recipe_request_failure(monkeypatch):
    def boom(*a, **k):
        raise llm.requests.RequestException("ollama down")

    monkeypatch.setattr(llm.requests, "post", boom)
    assert llm.generate_recipe("omelette") is None


def test_generate_recipe_blank_dish():
    assert llm.generate_recipe("   ") is None


# --- ask_in_recipe: mid-recipe question keeps recipe context ---------------

def test_ask_in_recipe_uses_context(monkeypatch):
    captured = {}

    def fake_ask(prompt):
        captured["p"] = prompt
        return "Medium heat."

    monkeypatch.setattr(llm, "ask", fake_ask)
    out = llm.ask_in_recipe("omelette", "Melt butter in a pan.", "how hot should the pan be?")
    assert out == "Medium heat."
    assert "omelette" in captured["p"]
    assert "Melt butter" in captured["p"]
    assert "how hot" in captured["p"]

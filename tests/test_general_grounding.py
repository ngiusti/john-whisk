from john_whisk import config, db, inventory, llm


class _Resp:
    def __init__(self, t):
        self._t = t

    def raise_for_status(self):
        pass

    def json(self):
        return {"response": self._t}


def test_ask_grounded_injects_pantry(monkeypatch):
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["payload"] = json
        return _Resp("ok")

    monkeypatch.setattr(llm.requests, "post", fake_post)
    llm.ask_grounded("what sauces do I have", "eggs, spinach, chicken")
    system = captured["payload"]["system"]
    assert "eggs, spinach, chicken" in system
    assert "never invent" in system.lower()


def test_ask_grounded_empty_pantry(monkeypatch):
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["p"] = json
        return _Resp("ok")

    monkeypatch.setattr(llm.requests, "post", fake_post)
    llm.ask_grounded("what do we have", "")
    assert "empty" in captured["p"]["system"].lower()


def test_ask_general_passes_real_pantry(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    db.add_items([{"name": "eggs", "quantity": None, "unit": None},
                  {"name": "spinach", "quantity": None, "unit": None}])
    captured = {}
    monkeypatch.setattr(llm, "ask_grounded",
                        lambda text, pantry: captured.setdefault("pantry", pantry) or "ok")
    inventory.ask_general("anything good to cook")
    assert "eggs" in captured["pantry"] and "spinach" in captured["pantry"]
    assert "chicken" not in captured["pantry"]     # only what's logged


def test_ask_general_empty_pantry(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    captured = {}
    monkeypatch.setattr(llm, "ask_grounded",
                        lambda text, pantry: captured.setdefault("pantry", pantry) or "ok")
    inventory.ask_general("hi there")
    assert captured["pantry"] == ""

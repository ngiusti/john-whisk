from john_whisk import config, db, llm, inventory


def test_add_from_text_stores_and_confirms(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(llm, "extract_items", lambda text: [
        {"name": "eggs", "quantity": 12, "unit": None},
        {"name": "spinach", "quantity": None, "unit": None},
    ])
    msg = inventory.add_from_text("whatever")
    assert msg.lower().startswith("added")
    assert "eggs" in msg and "spinach" in msg
    names = [i["name"] for i in db.get_inventory()]
    assert "eggs" in names and "spinach" in names


def test_add_from_text_no_items(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(llm, "extract_items", lambda text: [])
    assert "didn't catch" in inventory.add_from_text("whatever").lower()


def test_suggest_empty_pantry(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    assert "empty" in inventory.suggest("what can I make?").lower()


def test_suggest_with_stock_calls_llm(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    db.add_items([{"name": "eggs", "quantity": 12, "unit": None}])
    monkeypatch.setattr(llm, "ask", lambda prompt: "You could make an omelette.")
    reply = inventory.suggest("what can I make?")
    assert reply == "You could make an omelette."

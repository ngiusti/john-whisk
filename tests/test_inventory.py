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
    monkeypatch.setattr(llm, "suggest_recipe", lambda pantry, req: "You could make an omelette.")
    reply = inventory.suggest("what can I make?")
    assert reply == "You could make an omelette."


def test_suggest_passes_only_logged_items(tmp_path, monkeypatch):
    # the model must receive exactly what's in the DB and nothing invented
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    db.add_items([{"name": "eggs", "quantity": None, "unit": None},
                  {"name": "spinach", "quantity": None, "unit": None}])
    captured = {}
    monkeypatch.setattr(llm, "suggest_recipe",
                        lambda pantry, req: captured.setdefault("pantry", pantry) or "ok")
    inventory.suggest("what can I make?")
    assert "eggs" in captured["pantry"]
    assert "spinach" in captured["pantry"]
    assert "chicken" not in captured["pantry"]   # never anything that wasn't logged


def test_list_stock_reads_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    db.add_items([{"name": "eggs", "quantity": 12, "unit": None},
                  {"name": "spinach", "quantity": None, "unit": None}])
    msg = inventory.list_stock()
    assert "eggs" in msg and "spinach" in msg


def test_list_stock_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    assert "empty" in inventory.list_stock().lower()

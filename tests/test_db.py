from john_whisk import config, db


def test_add_and_get(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    db.add_items([{"name": "eggs", "quantity": 2, "unit": None}])
    assert db.get_inventory() == [{"name": "eggs", "quantity": 2.0, "unit": None}]


def test_merge_sums_numeric_quantities(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    db.add_items([{"name": "eggs", "quantity": 2, "unit": None}])
    db.add_items([{"name": "eggs", "quantity": 12, "unit": None}])
    inv = db.get_inventory()
    assert len(inv) == 1
    assert inv[0]["quantity"] == 14.0


def test_merge_with_vague_becomes_null(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    db.add_items([{"name": "spinach", "quantity": 2, "unit": None}])
    db.add_items([{"name": "spinach", "quantity": None, "unit": None}])
    assert db.get_inventory()[0]["quantity"] is None

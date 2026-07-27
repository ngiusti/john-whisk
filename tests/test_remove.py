from john_whisk import config, db, inventory, router


# --- router: the new "remove" intent -------------------------------------

def test_classify_out_of():
    assert router.classify("we're out of milk") == "remove"


def test_classify_ran_out():
    assert router.classify("I ran out of eggs") == "remove"


def test_classify_used_the_last():
    assert router.classify("used the last of the butter") == "remove"


def test_classify_no_more():
    assert router.classify("there's no more spinach") == "remove"


def test_remove_does_not_shadow_add():
    # buying is still an add, even though both touch inventory
    assert router.classify("I just bought milk") == "add"


def test_remove_does_not_shadow_suggest():
    assert router.classify("what can I make for dinner") == "suggest"


# --- deterministic name parsing (no LLM in the hot path) -----------------

def test_parse_single_item():
    assert inventory.parse_removed_names("we're out of milk") == ["milk"]


def test_parse_multiple_items():
    assert inventory.parse_removed_names("we're out of milk and eggs") == ["milk", "eggs"]


def test_parse_last_of_the():
    assert inventory.parse_removed_names("I used the last of the chicken") == ["chicken"]


def test_parse_multiword_item():
    assert inventory.parse_removed_names("we ran out of olive oil") == ["olive oil"]


def test_parse_nothing():
    assert inventory.parse_removed_names("we're out of") == []


# --- db: removal with singular/plural tolerance --------------------------

def test_db_remove_items(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    db.add_items([{"name": "milk", "quantity": 1, "unit": None}])
    assert db.remove_items(["milk"]) == ["milk"]
    assert db.get_inventory() == []


def test_db_remove_plural_tolerance(tmp_path, monkeypatch):
    # spoken plural "eggs" should still match the stored singular "egg"
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    db.add_items([{"name": "egg", "quantity": 12, "unit": None}])
    assert db.remove_items(["eggs"]) == ["egg"]
    assert db.get_inventory() == []


def test_db_remove_absent_item(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    db.add_items([{"name": "milk", "quantity": 1, "unit": None}])
    assert db.remove_items(["kale"]) == []
    assert [i["name"] for i in db.get_inventory()] == ["milk"]


# --- inventory: spoken end-to-end reply ----------------------------------

def test_remove_from_text_confirms(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    db.add_items([{"name": "milk", "quantity": 1, "unit": None}])
    msg = inventory.remove_from_text("we're out of milk")
    assert "milk" in msg
    assert db.get_inventory() == []


def test_remove_from_text_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    assert "didn't have" in inventory.remove_from_text("we're out of pine nuts").lower()


def test_remove_from_text_no_item(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    assert "didn't catch" in inventory.remove_from_text("we're out of").lower()

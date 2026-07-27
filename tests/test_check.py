from john_whisk import config, db, inventory, router


# --- router: the new "check" intent ---------------------------------------

def test_router_check_do_we_have_category():
    assert router.classify("do we have any sauces") == "check"


def test_router_check_do_we_have_item():
    assert router.classify("do we have milk") == "check"


def test_router_check_got_any():
    assert router.classify("got any butter") == "check"


def test_router_check_have_we_got():
    assert router.classify("have we got any bread") == "check"


def test_router_check_do_i_have():
    assert router.classify("do I have any spinach") == "check"


def test_router_check_is_there_any():
    assert router.classify("is there any cheese") == "check"


def test_router_list_still_wins_for_what_do_i_have():
    # "what do I have" is a full-pantry list, not a targeted check
    assert router.classify("what do I have") == "list"


def test_router_list_still_wins_for_what_do_i_have_left():
    assert router.classify("what do I have left") == "list"


# --- deterministic parse of the queried item ------------------------------

def test_parse_queried_category():
    assert inventory.parse_queried_names("do we have any sauces") == ["sauces"]


def test_parse_queried_item():
    assert inventory.parse_queried_names("do we have milk") == ["milk"]


def test_parse_queried_multiword():
    assert inventory.parse_queried_names("have we got any olive oil") == ["olive oil"]


# --- check answers straight from the DB (never the LLM) -------------------

def test_check_present(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    db.add_items([{"name": "milk", "quantity": None, "unit": None}])
    reply = inventory.check("do we have milk")
    assert reply.lower().startswith("yes")
    assert "milk" in reply.lower()


def test_check_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    db.add_items([{"name": "eggs", "quantity": None, "unit": None}])
    reply = inventory.check("do we have any sauces")
    assert reply.lower().startswith("no")
    assert "sauces" in reply.lower()


def test_check_absent_never_invents(tmp_path, monkeypatch):
    # the exact regression: it must not conjure sauces it doesn't have
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    db.add_items([{"name": "eggs", "quantity": None, "unit": None}])
    reply = inventory.check("do we have any sauces").lower()
    assert "marinara" not in reply and "alfredo" not in reply


def test_check_plural_tolerance(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    db.add_items([{"name": "egg", "quantity": None, "unit": None}])
    assert inventory.check("do we have any eggs").lower().startswith("yes")

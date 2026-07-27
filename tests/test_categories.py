import sqlite3

from john_whisk import config, db, inventory, llm


def _columns(dbfile):
    c = sqlite3.connect(dbfile)
    cols = [r[1] for r in c.execute("PRAGMA table_info(inventory)").fetchall()]
    c.close()
    return cols


class _Resp:
    def __init__(self, t):
        self._t = t

    def raise_for_status(self):
        pass

    def json(self):
        return {"response": self._t}


def _patch_extract(monkeypatch, json_text):
    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: _Resp(json_text))


# --- migration: an old DB without the column gets it, keeps its rows ---------

def test_migration_adds_category_column(tmp_path, monkeypatch):
    dbfile = str(tmp_path / "old.db")
    monkeypatch.setattr(config, "DB_PATH", dbfile)
    c = sqlite3.connect(dbfile)
    c.execute("CREATE TABLE inventory (id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
              "quantity REAL, unit TEXT, added_at TEXT NOT NULL)")
    c.execute("INSERT INTO inventory (name, quantity, unit, added_at) "
              "VALUES ('eggs', NULL, NULL, '2020-01-01')")
    c.commit()
    c.close()
    db.init_db()
    assert "category" in _columns(dbfile)
    assert [i["name"] for i in db.get_inventory()] == ["eggs"]   # row preserved


# --- storing + matching by category -----------------------------------------

def test_add_items_stores_category(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    db.add_items([{"name": "marinara", "quantity": None, "unit": None, "category": "sauce"}])
    assert db.get_inventory()[0]["category"] == "sauce"


def test_add_items_without_category_defaults_none(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    db.add_items([{"name": "milk", "quantity": None, "unit": None}])
    assert db.get_inventory()[0]["category"] is None


def test_match_query_by_name(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    db.add_items([{"name": "marinara", "quantity": None, "unit": None, "category": "sauce"}])
    assert db.match_query("marinara") == ["marinara"]


def test_match_query_by_category_plural(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    db.add_items([{"name": "marinara", "quantity": None, "unit": None, "category": "sauce"},
                  {"name": "alfredo", "quantity": None, "unit": None, "category": "sauce"},
                  {"name": "penne", "quantity": None, "unit": None, "category": "pasta"}])
    assert sorted(db.match_query("sauces")) == ["alfredo", "marinara"]


def test_match_query_no_match(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    db.add_items([{"name": "penne", "quantity": None, "unit": None, "category": "pasta"}])
    assert db.match_query("sauce") == []


def test_set_category(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    db.add_items([{"name": "chicken", "quantity": None, "unit": None}])
    db.set_category("chicken", "protein")
    assert db.get_inventory()[0]["category"] == "protein"


# --- extraction assigns a validated category --------------------------------

def test_extract_reads_category(monkeypatch):
    _patch_extract(monkeypatch,
                   '{"items":[{"name":"marinara","quantity":null,"unit":null,"category":"sauce"}]}')
    assert llm.extract_items("I bought marinara")[0]["category"] == "sauce"


def test_extract_invalid_category_falls_back(monkeypatch):
    _patch_extract(monkeypatch,
                   '{"items":[{"name":"marinara","quantity":null,"unit":null,"category":"topping"}]}')
    assert llm.extract_items("x")[0]["category"] == "other"


def test_extract_missing_category_falls_back(monkeypatch):
    _patch_extract(monkeypatch,
                   '{"items":[{"name":"marinara","quantity":null,"unit":null}]}')
    assert llm.extract_items("x")[0]["category"] == "other"


# --- parsing category questions in any position -----------------------------

def test_parse_what_kind_of():
    assert inventory.parse_queried_names("what kind of pasta do I have") == ["pasta"]


def test_parse_what_x_do_i_have():
    assert inventory.parse_queried_names("what sauces do I have") == ["sauces"]


def test_parse_do_we_have_any_still_works():
    assert inventory.parse_queried_names("do we have any sauces") == ["sauces"]


def test_parse_multiword_still_works():
    assert inventory.parse_queried_names("have we got any olive oil") == ["olive oil"]


# --- check lists items by category ------------------------------------------

def test_check_category_lists_items(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    db.add_items([{"name": "marinara", "quantity": None, "unit": None, "category": "sauce"},
                  {"name": "alfredo", "quantity": None, "unit": None, "category": "sauce"}])
    reply = inventory.check("do we have any sauces").lower()
    assert reply.startswith("yes")
    assert "marinara" in reply and "alfredo" in reply


def test_check_category_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    db.add_items([{"name": "penne", "quantity": None, "unit": None, "category": "pasta"}])
    reply = inventory.check("do we have any sauces").lower()
    assert reply.startswith("no") and "sauces" in reply


def test_check_dedupes_name_and_category(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    db.add_items([{"name": "marinara", "quantity": None, "unit": None, "category": "sauce"}])
    assert inventory.check("do we have marinara").lower().count("marinara") == 1

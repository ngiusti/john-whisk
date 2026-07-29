import json
from john_whisk import config, nutrition


def _fixture_seed(tmp_path, monkeypatch):
    """Isolate the nutrition DB + point the seed at a small fixture."""
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "n.db"))
    seed = tmp_path / "nutrition.json"
    seed.write_text(json.dumps([
        {"name": "egg", "aliases": ["eggs"],
         "per_100g": {"calories": 143, "protein": 12.6, "carbs": 0.7, "fat": 9.5},
         "portions": {"each": 50, "large": 50}},
        {"name": "rice", "aliases": ["white rice"],
         "per_100g": {"calories": 130, "protein": 2.7, "carbs": 28, "fat": 0.3},
         "portions": {"cup": 158}},
    ]))
    monkeypatch.setattr(config, "NUTRITION_SEED_PATH", str(seed))


def test_lookup_by_name(tmp_path, monkeypatch):
    _fixture_seed(tmp_path, monkeypatch)
    r = nutrition.lookup("rice")
    assert r["per_100g"]["calories"] == 130
    assert r["portions"]["cup"] == 158


def test_lookup_by_alias_and_plural(tmp_path, monkeypatch):
    _fixture_seed(tmp_path, monkeypatch)
    assert nutrition.lookup("eggs")["per_100g"]["protein"] == 12.6      # alias/plural


def test_lookup_word_subset(tmp_path, monkeypatch):
    _fixture_seed(tmp_path, monkeypatch)
    assert nutrition.lookup("cooked white rice") is not None            # entry words ⊆ query


def test_lookup_miss_returns_none(tmp_path, monkeypatch):
    _fixture_seed(tmp_path, monkeypatch)
    assert nutrition.lookup("saffron") is None


import pytest


@pytest.mark.parametrize("line,qty,unit,food", [
    ("1 cup uncooked rice", 1.0, "cup", "uncooked rice"),
    ("2 eggs", 2.0, None, "eggs"),
    ("1/2 cup sugar", 0.5, "cup", "sugar"),
    ("1 1/2 cups flour", 1.5, "cup", "flour"),
    ("½ cup butter", 0.5, "cup", "butter"),
    ("2 tablespoons olive oil", 2.0, "tablespoon", "olive oil"),
    ("a pinch of salt", 1.0, "pinch", "salt"),
    ("salt to taste", None, None, "salt to taste"),
])
def test_parse_ingredient(line, qty, unit, food):
    assert nutrition.parse_ingredient(line) == (qty, unit, food)


def test_parse_ingredient_zero_denominator_does_not_crash():
    # malformed fraction must not raise ZeroDivisionError
    assert nutrition.parse_ingredient("1/0 cup sugar") == (None, None, "1/0 cup sugar")
    # the integer is kept; the malformed fraction is left in the food text
    assert nutrition.parse_ingredient("1 1/0 cups flour") == (1.0, None, "1/0 cups flour")


def test_to_grams_food_portion(tmp_path, monkeypatch):
    _fixture_seed(tmp_path, monkeypatch)
    assert nutrition.to_grams(1, "cup", "rice") == 158           # food's own portion


def test_to_grams_count_each(tmp_path, monkeypatch):
    _fixture_seed(tmp_path, monkeypatch)
    assert nutrition.to_grams(2, None, "eggs") == 100            # 2 * each(50)


def test_to_grams_mass_unit(tmp_path, monkeypatch):
    _fixture_seed(tmp_path, monkeypatch)
    assert nutrition.to_grams(200, "gram", "rice") == 200        # direct mass


def test_to_grams_generic_volume(tmp_path, monkeypatch):
    _fixture_seed(tmp_path, monkeypatch)
    # no "tablespoon" portion for rice -> generic approximation (15 g)
    assert nutrition.to_grams(2, "tablespoon", "rice") == 30


def test_to_grams_unconvertible(tmp_path, monkeypatch):
    _fixture_seed(tmp_path, monkeypatch)
    assert nutrition.to_grams(1, "pinch", "rice") is None


from john_whisk import llm


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_estimate_nutrition_parses_json(monkeypatch):
    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: _Resp(
        {"response": '{"calories": 200, "protein": 6, "carbs": 30, "fat": 5}'}))
    out = llm.estimate_nutrition("one bagel")
    assert out == {"calories": 200.0, "protein": 6.0, "carbs": 30.0, "fat": 5.0}


def test_estimate_nutrition_failure_returns_none(monkeypatch):
    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: _Resp({"response": "nope"}))
    assert llm.estimate_nutrition("one bagel") is None

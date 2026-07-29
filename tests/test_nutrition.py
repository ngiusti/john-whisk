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

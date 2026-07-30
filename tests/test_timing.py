"""Time-based filtering: estimate minutes, parse a spoken budget, filter the
library. RECIPES_DB_PATH is isolated per test."""
from john_whisk import config, recipes, timing


def _fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RECIPES_DB_PATH", str(tmp_path / "r.db"))


def test_estimate_minutes_from_steps():
    assert timing.estimate_minutes({"steps": ["a", "b", "c"]}) == 5 + 12   # base + 3 steps


def test_estimate_minutes_slow_keywords():
    m = timing.estimate_minutes({"steps": ["Mix it.", "Bake in the oven until golden."]})
    assert m >= 5 + 8 + 25          # base + 2 steps + bake bonus


def test_parse_minutes():
    assert timing.parse_minutes("what can I make in 20 minutes") == 20
    assert timing.parse_minutes("something in half an hour") == 30
    assert timing.parse_minutes("in an hour") == 60
    assert timing.parse_minutes("something quick") == 20


def test_quick_recipes_filters(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    recipes.add_recipe("Fast Salad", "greens", ["Toss.", "Serve."])              # ~13 min
    recipes.add_recipe("Slow Roast", "beef", ["Season.", "Roast for hours.", "Rest."])  # +55
    titles = [h["title"] for h in timing.quick_recipes(20)]
    assert "Fast Salad" in titles and "Slow Roast" not in titles


def test_quick_recipes_caches_minutes(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    recipes.add_recipe("Fast Salad", "greens", ["Toss.", "Serve."])
    timing.quick_recipes(60)
    import contextlib
    import sqlite3
    with contextlib.closing(sqlite3.connect(config.RECIPES_DB_PATH)) as c:
        val = c.execute("SELECT minutes FROM recipes WHERE title = 'Fast Salad'").fetchone()[0]
    assert val == 13                # cached on the row


def test_answer_quick(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    recipes.add_recipe("Fast Salad", "greens", ["Toss.", "Serve."])
    assert "fast salad" in timing.answer_quick("what can I make in 20 minutes").lower()


def test_router_quick_intent():
    from john_whisk import router
    assert router.classify("what can I make in 20 minutes") == "quick"
    assert router.classify("something quick for dinner") == "quick"

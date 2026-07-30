"""Seasonal & budget modes. `now`/`month` injected; RECIPES_DB_PATH isolated."""
import datetime

from john_whisk import config, recipes, seasonal


def _fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RECIPES_DB_PATH", str(tmp_path / "r.db"))


def test_in_season_by_month():
    assert "tomato" in seasonal.in_season(7)     # July
    assert "kale" in seasonal.in_season(1)       # January


def test_answer_in_season():
    s = seasonal.answer_in_season(now=datetime.datetime(2026, 7, 15))
    assert "tomato" in s.lower()


def test_seasonal_recipes_matches_produce(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    recipes.add_recipe("Tomato Salad", "2 tomatoes, basil, olive oil", ["Toss."])
    recipes.add_recipe("Beef Stew", "beef, flour, gravy", ["Simmer."])
    titles = [r["title"] for r in seasonal.seasonal_recipes(7)]   # July -> tomato
    assert "Tomato Salad" in titles and "Beef Stew" not in titles


def test_budget_excludes_expensive(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    recipes.add_recipe("Bean Bowl", "beans, rice, onion", ["Cook."])
    recipes.add_recipe("Lobster Feast", "lobster, saffron, cream", ["Cook."])
    titles = [r["title"] for r in seasonal.budget_recipes()]
    assert "Bean Bowl" in titles and "Lobster Feast" not in titles


def test_answer_budget(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    recipes.add_recipe("Bean Bowl", "beans, rice, onion", ["Cook."])
    assert "bean bowl" in seasonal.answer_budget().lower()


def test_router_seasonal_and_budget():
    from john_whisk import router
    assert router.classify("what's in season") == "seasonal"
    assert router.classify("what can I make on a budget") == "budget"
    assert router.classify("cheap meals") == "budget"

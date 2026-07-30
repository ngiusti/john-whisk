"""Phase B: daily intake log + goals. DB isolated to a temp file; the seed is a
small fixture; the LLM is never hit (all fixture foods resolve locally)."""
import contextlib
import json
import sqlite3

import pytest

from john_whisk import config, nutrition


def _seed(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "n.db"))
    seed = tmp_path / "nutrition.json"
    seed.write_text(json.dumps([
        {"name": "egg", "aliases": ["eggs"],
         "per_100g": {"calories": 143, "protein": 12.6, "carbs": 0.7, "fat": 9.5},
         "portions": {"each": 50}},
        {"name": "rice", "aliases": ["white rice"],
         "per_100g": {"calories": 130, "protein": 2.7, "carbs": 28, "fat": 0.3},
         "portions": {"cup": 158}},
        {"name": "toast", "aliases": ["bread"],
         "per_100g": {"calories": 265, "protein": 9, "carbs": 49, "fat": 3.2},
         "portions": {"slice": 28, "each": 28}},
    ]))
    monkeypatch.setattr(config, "NUTRITION_SEED_PATH", str(seed))


def test_log_food_and_today(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    nutrition.log_food("I ate two eggs")
    assert nutrition.today()["calories"] == 143          # 2 eggs = 100 g


def test_log_multiple_foods(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    reply = nutrition.log_food("log two eggs and one slice of toast")
    assert nutrition.today()["calories"] > 200           # 143 + ~74
    assert "egg" in reply.lower()


def test_today_excludes_other_dates(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    nutrition.log_food("two eggs")
    with contextlib.closing(sqlite3.connect(config.DB_PATH)) as c:
        c.execute("INSERT INTO daily_log (log_date, food, calories, protein, carbs, fat, logged_at) "
                  "VALUES (?, ?, ?, ?, ?, ?, ?)",
                  ("2000-01-01", "old", 999, 1, 1, 1, "2000-01-01T00:00:00"))
        c.commit()
    assert nutrition.today()["calories"] == 143          # yesterday's 999 excluded


def test_goals_set_and_get(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    nutrition.set_goal("calories", 2000)
    nutrition.set_goal("protein", 150)
    g = nutrition.goals()
    assert g["calories"] == 2000 and g["protein"] == 150 and g["carbs"] is None


def test_set_goal_from_text(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    reply = nutrition.set_goal_from_text("set my calorie goal to 2000")
    assert nutrition.goals()["calories"] == 2000 and "2000" in reply


def test_remaining(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    nutrition.set_goal("calories", 2000)
    nutrition.log_food("two eggs")
    r = nutrition.remaining()
    assert r["calories"] == pytest.approx(2000 - 143, abs=0.5)
    assert r["protein"] is None                          # no protein goal set


def test_answer_status(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    nutrition.set_goal("calories", 2000)
    nutrition.log_food("two eggs")
    s = nutrition.answer_status()
    assert "143" in s and "2000" in s


def test_answer_status_empty(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    assert "haven't logged" in nutrition.answer_status().lower()


def test_answer_query_routes_status(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    nutrition.set_goal("calories", 2000)
    nutrition.log_food("two eggs")
    assert "143" in nutrition.answer_query("how am I doing today")


def test_log_serving_of_recipe(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    from john_whisk import recipes
    monkeypatch.setattr(config, "RECIPES_DB_PATH", str(tmp_path / "r.db"))
    recipes.add_recipe("Egg Rice", "2 eggs, 1 cup rice", ["a", "b"])
    reply = nutrition.log_food("I ate a serving of egg rice")
    assert "egg rice" in reply.lower()
    assert nutrition.today()["calories"] > 0


def test_goal_command_reports_when_no_number(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    nutrition.set_goal("calories", 2000)
    assert "2000" in nutrition.goal_command("what are my goals")


def test_today_entries_and_remove(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    nutrition.log_food("two eggs")
    entries = nutrition.today_entries()
    assert len(entries) == 1 and entries[0]["food"] == "two eggs"
    nutrition.remove_log(entries[0]["id"])
    assert nutrition.today_entries() == []

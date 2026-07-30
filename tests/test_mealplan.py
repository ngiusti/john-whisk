"""Meal-planning calendar (Phase 1). `now` injected; DB_PATH isolated."""
import datetime

from john_whisk import config, mealplan

# A fixed reference: 2026-07-15 is a Wednesday.
NOW = datetime.datetime(2026, 7, 15, 12, 0, 0)


def _fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "p.db"))


def test_parse_today_tomorrow():
    assert mealplan.parse_date("tonight", NOW) == datetime.date(2026, 7, 15)
    assert mealplan.parse_date("tomorrow", NOW) == datetime.date(2026, 7, 16)


def test_parse_weekday_soonest():
    # Wed 7/15 -> "friday" is 7/17; "wednesday" is today
    assert mealplan.parse_date("friday", NOW) == datetime.date(2026, 7, 17)
    assert mealplan.parse_date("wednesday", NOW) == datetime.date(2026, 7, 15)


def test_parse_next_weekday():
    assert mealplan.parse_date("next friday", NOW) == datetime.date(2026, 7, 24)


def test_parse_in_n_days_and_explicit():
    assert mealplan.parse_date("in 3 days", NOW) == datetime.date(2026, 7, 18)
    assert mealplan.parse_date("august 4th", NOW) == datetime.date(2026, 8, 4)
    assert mealplan.parse_date("the 20th", NOW) == datetime.date(2026, 7, 20)


def test_parse_past_dayofmonth_rolls_to_next_month():
    # the 5th already passed on the 15th -> next month
    assert mealplan.parse_date("the 5th", NOW) == datetime.date(2026, 8, 5)


def test_parse_unparseable_returns_none():
    assert mealplan.parse_date("sometime soon", NOW) is None


def test_mentions_day():
    assert mealplan.mentions_day("what am I making friday")
    assert mealplan.mentions_day("what's the plan this week")
    assert not mealplan.mentions_day("what am I making right now")


def test_add_and_query_plan(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    reply = mealplan.handle_set("plan chicken alfredo for friday", NOW)
    assert "chicken alfredo" in reply.lower() and "friday" in reply.lower()
    assert mealplan.plan_for("2026-07-17") == ["chicken alfredo"]


def test_multiple_dishes_per_day(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    mealplan.handle_set("plan tacos for friday", NOW)
    mealplan.handle_set("put salad on the menu friday", NOW)
    assert mealplan.plan_for("2026-07-17") == ["tacos", "salad"]


def test_query_specific_day(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    mealplan.add_plan("2026-07-17", "chicken alfredo")
    assert "chicken alfredo" in mealplan.handle_query("what am I making friday", NOW).lower()


def test_query_empty_day(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    assert "nothing planned" in mealplan.handle_query("what's on the menu tomorrow", NOW).lower()


def test_query_week(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    mealplan.add_plan("2026-07-17", "tacos")     # Friday, within the week
    out = mealplan.handle_query("what's my plan this week", NOW)
    assert "tacos" in out.lower()


def test_handle_set_no_date_prompts(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    assert "which day" in mealplan.handle_set("plan tacos", NOW).lower()


def test_remove_and_clear(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    mealplan.add_plan("2026-07-17", "tacos")
    entries = mealplan.plan_entries("2026-07-17")
    mealplan.remove_plan(entries[0]["id"])
    assert mealplan.plan_for("2026-07-17") == []


def test_router_plan_intents():
    from john_whisk import router
    assert router.classify("plan chicken alfredo for friday") == "plan_set"
    assert router.classify("put tacos on the menu tomorrow") == "plan_set"
    assert router.classify("what's on the menu tonight") == "plan_query"
    assert router.classify("what's my meal plan this week") == "plan_query"


def test_router_plan_does_not_break_grocery_plan():
    # the grocery meal-planner keeps "plan to make X" / "I would like to make X"
    from john_whisk import router
    assert router.classify("I would like to make lasagna") == "plan"
    assert router.classify("plan to make lasagna") == "plan"

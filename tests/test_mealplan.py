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


def test_parse_time():
    assert mealplan.parse_time("august 20th at 4pm") == (16, 0)
    assert mealplan.parse_time("at 4:30 pm") == (16, 30)
    assert mealplan.parse_time("at noon") == (12, 0)
    assert mealplan.parse_time("midnight") == (0, 0)
    assert mealplan.parse_time("at 16:00") == (16, 0)
    assert mealplan.parse_time("at 9 in the morning") == (9, 0)
    assert mealplan.parse_time("at 4 in the afternoon") == (16, 0)
    assert mealplan.parse_time("12am") == (0, 0)
    assert mealplan.parse_time("august 20th") is None       # no time -> None


def test_parse_datetime():
    import datetime
    d, tm = mealplan.parse_datetime("august 20th at 4pm", NOW)
    assert d == datetime.date(2026, 8, 20) and tm == (16, 0)


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


# --- Phase 2: events, holidays, upcoming ----------------------------------

def test_holiday_on_fixed_and_thanksgiving():
    assert mealplan.holiday_on(datetime.date(2026, 12, 25)) == "Christmas"
    assert mealplan.holiday_on(datetime.date(2026, 7, 4)) == "Independence Day"
    # Thanksgiving 2026 = 4th Thursday of Nov = Nov 26
    assert mealplan.holiday_on(datetime.date(2026, 11, 26)) == "Thanksgiving"
    assert mealplan.holiday_on(datetime.date(2026, 3, 3)) is None


def test_add_and_query_event(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    reply = mealplan.handle_event_add("I have dinner plans thursday", NOW)
    assert "dinner plans" in reply.lower()
    assert mealplan.events_for("2026-07-16") == ["dinner plans"]   # Thu 7/16 (= tomorrow)


def test_event_no_date_prompts(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    assert "which day" in mealplan.handle_event_add("I have plans", NOW).lower()


def test_upcoming_combines(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    mealplan.add_plan("2026-07-17", "tacos")               # Fri
    mealplan.add_event("2026-07-16", "dentist")            # Thu
    u = mealplan.upcoming(NOW, days=7)
    assert any(m["dish"] == "tacos" for m in u["meals"])
    assert any(e["description"] == "dentist" for e in u["events"])
    assert u["season"]                                     # July produce present


def test_answer_upcoming_mentions_items(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    mealplan.add_plan("2026-07-17", "tacos")
    mealplan.add_event("2026-07-16", "dentist")
    s = mealplan.answer_upcoming("what's coming up this week", NOW)
    assert "tacos" in s.lower() and "dentist" in s.lower()


def test_answer_upcoming_empty_falls_back_to_season(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    s = mealplan.answer_upcoming("what's coming up", NOW)
    assert "nothing on the calendar" in s.lower() and "season" in s.lower()


def test_router_event_and_calendar_intents():
    from john_whisk import router
    assert router.classify("I have dinner plans thursday") == "event_add"
    assert router.classify("remind me about the dentist friday") == "event_add"
    assert router.classify("what's coming up this week") == "calendar_query"
    assert router.classify("anything going on this weekend") == "calendar_query"


def test_event_add_does_not_shadow_equipment():
    from john_whisk import router
    assert router.classify("I have a blender") == "equipment"


# --- Phase 3: auto features -----------------------------------------------

def test_planning_auto_adds_missing_to_grocery(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    from john_whisk import recipes, grocery
    recipes.add_recipe("Chicken Alfredo", "chicken, pasta, cream, parmesan", ["Cook."])
    reply = mealplan.handle_set("plan chicken alfredo for friday", NOW)
    assert "grocery" in reply.lower()
    assert any("cream" in g.lower() for g in grocery.items())


def test_is_planned_log():
    assert mealplan.is_planned_log("I ate my planned dinner")
    assert not mealplan.is_planned_log("I ate two eggs")


def test_calendar_add_confirms_before_writing(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    from john_whisk import calwrite, calsync
    monkeypatch.setattr(calwrite, "available", lambda: True)
    cap = {}
    monkeypatch.setattr(calwrite, "create_event",
                        lambda summary, start, **k: cap.update(summary=summary, start=start)
                        or {"ok": True, "link": "x"})
    monkeypatch.setattr(calsync, "sync", lambda now=None: 0)
    ask = mealplan.handle_calendar_add(
        "add a dentist appointment to my calendar august 20th at 4pm", NOW)
    assert "should i" in ask.lower() and "dentist" in ask.lower()
    assert not cap                                     # NOTHING written until confirmed
    done = mealplan.confirm_pending()
    assert "google calendar" in done.lower()
    assert cap["summary"].lower().startswith("dentist")
    assert cap["start"] == datetime.datetime(2026, 8, 20, 16, 0)


def test_calendar_add_confirm_falls_back_local(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    from john_whisk import calwrite
    monkeypatch.setattr(calwrite, "available", lambda: False)
    mealplan.handle_calendar_add("add an appointment to my calendar august 20th at 4pm", NOW)
    reply = mealplan.confirm_pending()
    assert "saved" in reply.lower()
    assert mealplan.events_for("2026-08-20") == ["appointment"]


def test_confirm_reply():
    assert mealplan.confirm_reply("yes please") == "yes"
    assert mealplan.confirm_reply("no, cancel that") == "no"
    assert mealplan.confirm_reply("never mind") == "no"
    assert mealplan.confirm_reply("what's for dinner") is None


def test_calendar_edit_delete(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    from john_whisk import calwrite, calsync
    monkeypatch.setattr(calwrite, "list_events", lambda **k: [
        {"id": "e1", "summary": "dentist appointment", "start": "2026-08-21T12:00:00-07:00"}])
    seen = {}
    monkeypatch.setattr(calwrite, "delete_event", lambda eid: seen.update(id=eid) or True)
    monkeypatch.setattr(calsync, "sync", lambda now=None: 0)
    ask = mealplan.handle_calendar_edit("delete the appointment on august 21st", NOW)
    assert "delete" in ask.lower() and "dentist" in ask.lower()
    done = mealplan.confirm_pending()
    assert "deleted" in done.lower() and seen["id"] == "e1"


def test_calendar_edit_rename(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    from john_whisk import calwrite, calsync
    monkeypatch.setattr(calwrite, "list_events", lambda **k: [
        {"id": "e1", "summary": "dent disappointment", "start": "2026-08-21T12:00:00-07:00"}])
    seen = {}
    monkeypatch.setattr(calwrite, "update_summary",
                        lambda eid, s: seen.update(id=eid, s=s) or True)
    monkeypatch.setattr(calsync, "sync", lambda now=None: 0)
    ask = mealplan.handle_calendar_edit(
        "rename the appointment on august 21st to dentist appointment", NOW)
    assert "rename" in ask.lower()
    done = mealplan.confirm_pending()
    assert seen["s"] == "dentist appointment" and "renamed" in done.lower()


def test_router_calendar_edit():
    from john_whisk import router
    assert router.classify("delete the appointment on friday") == "calendar_edit"
    assert router.classify("rename the appointment to dentist") == "calendar_edit"


def test_router_calendar_add():
    from john_whisk import router
    assert router.classify("add an appointment to my calendar august 20th at 4pm") == "calendar_add"
    assert router.classify("what's on my calendar this week") == "calendar_query"
    assert router.classify("I have an appointment friday") == "event_add"


def test_router_calendar_add_forgiving_phrasings():
    from john_whisk import router
    # action verb + "calendar" -> write, even without the exact old triggers
    assert router.classify("put a lunch with mom on my calendar friday") == "calendar_add"
    assert router.classify("schedule a dentist visit on my calendar next monday") == "calendar_add"
    # broadened read phrasings
    assert router.classify("what appointments do I have in august") == "calendar_query"
    assert router.classify("what's on the calendar this weekend") == "calendar_query"


def test_clarify_nudges_calendar_misses():
    assert "calendar" in mealplan.clarify("something something appointment").lower()
    assert mealplan.clarify("what's a good pasta recipe") is None


def test_log_planned_feeds_nutrition(tmp_path, monkeypatch):
    import json
    _fresh(tmp_path, monkeypatch)
    from john_whisk import recipes, nutrition
    seed = tmp_path / "nutrition.json"
    seed.write_text(json.dumps([
        {"name": "egg", "aliases": ["eggs"],
         "per_100g": {"calories": 143, "protein": 12.6, "carbs": 0.7, "fat": 9.5},
         "portions": {"each": 50}}]))
    monkeypatch.setattr(config, "NUTRITION_SEED_PATH", str(seed))
    recipes.add_recipe("Egg Dish", "2 eggs", ["Cook."])
    mealplan.add_plan(NOW.date().isoformat(), "Egg Dish")
    reply = mealplan.log_planned("I ate my planned dinner", NOW)
    assert "egg dish" in reply.lower()
    assert nutrition.today()["calories"] > 0

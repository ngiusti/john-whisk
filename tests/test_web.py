import json

import pytest

from john_whisk import config, web, recipes


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "p.db"))
    monkeypatch.setattr(config, "RECIPES_DB_PATH", str(tmp_path / "r.db"))
    seed = tmp_path / "nutrition.json"
    seed.write_text(json.dumps([
        {"name": "egg", "aliases": ["eggs"],
         "per_100g": {"calories": 143, "protein": 12.6, "carbs": 0.7, "fat": 9.5},
         "portions": {"each": 50}},
    ]))
    monkeypatch.setattr(config, "NUTRITION_SEED_PATH", str(seed))
    app = web.create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_index_serves_html(client):
    r = client.get("/")
    assert r.status_code == 200 and b"John Whisk" in r.data


def test_grocery_flow(client):
    assert client.get("/api/grocery").get_json()["items"] == []
    client.post("/api/grocery", json={"item": "milk"})
    assert "milk" in client.get("/api/grocery").get_json()["items"]
    client.post("/api/grocery/remove", json={"item": "milk"})
    assert client.get("/api/grocery").get_json()["items"] == []


def test_grocery_clear(client):
    client.post("/api/grocery", json={"item": "milk"})
    client.post("/api/grocery/clear")
    assert client.get("/api/grocery").get_json()["items"] == []


def test_pantry_flow(client):
    client.post("/api/pantry", json={"name": "eggs"})
    names = [i["name"] for i in client.get("/api/pantry").get_json()["items"]]
    assert "eggs" in names
    client.post("/api/pantry/remove", json={"name": "eggs"})
    names = [i["name"] for i in client.get("/api/pantry").get_json()["items"]]
    assert "eggs" not in names


def test_recipes_search_and_view(client):
    recipes.add_recipe("Chicken Alfredo", "chicken, cream", ["Cook.", "Serve."])
    results = client.get("/api/recipes?q=alfredo").get_json()["results"]
    assert any("Alfredo" in r["title"] for r in results)
    v = client.get("/api/recipes/view?title=Chicken Alfredo").get_json()
    assert v["steps"] == ["Cook.", "Serve."] and v["title"] == "Chicken Alfredo"


def test_recipes_view_unknown_404(client):
    assert client.get("/api/recipes/view?title=definitely-not-a-recipe").status_code == 404


def test_settings_flow(client):
    client.post("/api/restrictions", json={"item": "dairy"})
    client.post("/api/equipment", json={"item": "blender"})
    client.post("/api/flavor", json={"item": "mild"})
    s = client.get("/api/settings").get_json()
    assert "dairy" in s["restrictions"]
    assert "blender" in s["equipment"]
    assert "mild" in s["flavor"]
    client.post("/api/restrictions/remove", json={"item": "dairy"})
    assert "dairy" not in client.get("/api/settings").get_json()["restrictions"]


def test_bad_post_returns_400(client):
    assert client.post("/api/grocery", json={}).status_code == 400


def test_nutrition_status_empty(client):
    r = client.get("/api/nutrition").get_json()
    assert r["totals"]["calories"] == 0 and r["entries"] == []


def test_nutrition_log_and_remove(client):
    client.post("/api/nutrition/log", json={"item": "two eggs"})
    r = client.get("/api/nutrition").get_json()
    assert r["totals"]["calories"] == 143 and len(r["entries"]) == 1
    eid = r["entries"][0]["id"]
    client.post("/api/nutrition/log/remove", json={"id": eid})
    assert client.get("/api/nutrition").get_json()["entries"] == []


def test_nutrition_goal_flow(client):
    client.post("/api/nutrition/goal", json={"field": "calories", "value": 2000})
    r = client.get("/api/nutrition").get_json()
    assert r["goals"]["calories"] == 2000 and r["remaining"]["calories"] == 2000


def test_nutrition_goal_bad_field_400(client):
    assert client.post("/api/nutrition/goal",
                       json={"field": "banana", "value": 1}).status_code == 400


def test_pantry_includes_expiration_status(client):
    client.post("/api/pantry", json={"name": "eggs"})
    items = client.get("/api/pantry").get_json()["items"]
    assert items and "status" in items[0] and "days_left" in items[0]


def test_recipes_quick_endpoint(client):
    recipes.add_recipe("Fast Salad", "greens", ["Toss.", "Serve."])
    recipes.add_recipe("Slow Roast", "beef", ["Season.", "Roast for hours.", "Rest."])
    r = client.get("/api/recipes/quick?max=20").get_json()
    titles = [x["title"] for x in r["results"]]
    assert "Fast Salad" in titles and "Slow Roast" not in titles and r["max"] == 20


def test_recipes_budget_endpoint(client):
    recipes.add_recipe("Bean Bowl", "beans, rice, onion", ["Cook."])
    recipes.add_recipe("Lobster Feast", "lobster, saffron", ["Cook."])
    titles = [x["title"] for x in client.get("/api/recipes/budget").get_json()["results"]]
    assert "Bean Bowl" in titles and "Lobster Feast" not in titles


def test_plan_endpoints(client):
    import datetime
    today = datetime.date.today().isoformat()
    client.post("/api/plan", json={"date": today, "dish": "tacos"})
    days = client.get("/api/plan?days=7").get_json()["days"]
    match = [e for d in days for e in d["entries"] if e["dish"] == "tacos"]
    assert match
    client.post("/api/plan/remove", json={"id": match[0]["id"]})
    days2 = client.get("/api/plan?days=7").get_json()["days"]
    assert not any(e["dish"] == "tacos" for d in days2 for e in d["entries"])


def test_plan_add_bad_request(client):
    assert client.post("/api/plan", json={"date": "2026-01-01"}).status_code == 400


def test_event_endpoints(client):
    import datetime
    today = datetime.date.today().isoformat()
    client.post("/api/event", json={"date": today, "description": "dentist"})
    days = client.get("/api/plan?days=7").get_json()["days"]
    match = [e for d in days for e in d["events"] if e["description"] == "dentist"]
    assert match
    client.post("/api/event/remove", json={"id": match[0]["id"]})
    days2 = client.get("/api/plan?days=7").get_json()["days"]
    assert not any(e["description"] == "dentist" for d in days2 for e in d["events"])


def test_online_settings_flow(client):
    r0 = client.get("/api/online-settings").get_json()
    assert r0["online_enabled"] is True and r0["has_fdc_key"] is False
    client.post("/api/online-settings",
                json={"online_enabled": False, "location": "Denver", "fdc_key": "SECRET"})
    r1 = client.get("/api/online-settings").get_json()
    assert r1["online_enabled"] is False and r1["location"] == "Denver"
    assert r1["has_fdc_key"] is True and "SECRET" not in str(r1)   # secret not echoed


def test_calendar_sync_endpoint_no_url(client):
    # no iCal URL configured -> ok False, count None (graceful)
    r = client.post("/api/calendar/sync").get_json()
    assert r["ok"] is False and r["count"] is None

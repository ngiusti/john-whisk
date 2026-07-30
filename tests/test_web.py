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

import json

from john_whisk import config, recipes, recipe_import


def _fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RECIPES_DB_PATH", str(tmp_path / "r.db"))


HTML_HOWTOSTEP = """
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Recipe","name":"Test Pancakes",
"recipeIngredient":["1 cup flour","1 egg","1 cup milk"],
"recipeInstructions":[{"@type":"HowToStep","text":"Mix the batter."},
{"@type":"HowToStep","text":"Cook on a griddle."}]}
</script></head><body>hi</body></html>
"""

HTML_STRING_STEPS = """
<script type="application/ld+json">
{"@type":"Recipe","name":"Simple Toast","recipeIngredient":["bread","butter"],
"recipeInstructions":"Toast the bread. Butter it."}
</script>
"""

HTML_GRAPH = """
<script type="application/ld+json">
{"@context":"https://schema.org","@graph":[
{"@type":"WebPage","name":"page"},
{"@type":"Recipe","name":"Graph Soup","recipeIngredient":["broth","carrot"],
"recipeInstructions":[{"@type":"HowToStep","text":"Simmer."}]}]}
</script>
"""

HTML_NO_RECIPE = "<html><body><p>Just a blog post, no recipe.</p></body></html>"


# --- parsing (pure, no network) -------------------------------------------

def test_parse_howtostep():
    r = recipe_import.parse_recipe_html(HTML_HOWTOSTEP, source="http://x/p")
    assert r["title"] == "Test Pancakes"
    assert r["ingredients"] == "1 cup flour, 1 egg, 1 cup milk"
    assert r["steps"] == ["Mix the batter.", "Cook on a griddle."]
    assert r["source"] == "http://x/p"


def test_parse_string_instructions():
    r = recipe_import.parse_recipe_html(HTML_STRING_STEPS)
    assert r["title"] == "Simple Toast"
    assert len(r["steps"]) == 2                  # split into two sentences


def test_parse_graph():
    r = recipe_import.parse_recipe_html(HTML_GRAPH)
    assert r["title"] == "Graph Soup" and r["steps"] == ["Simmer."]


def test_parse_no_recipe_returns_none():
    assert recipe_import.parse_recipe_html(HTML_NO_RECIPE) is None


# --- import_url -----------------------------------------------------------

def test_import_url_adds(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    monkeypatch.setattr(recipe_import, "parse_recipe_page",
                        lambda url: {"title": "Pie", "ingredients": "apples",
                                     "steps": ["Bake."], "source": url})
    assert recipe_import.import_url("http://x/pie") is True
    assert recipes.count() == 1


# --- import_dataset -------------------------------------------------------

def test_import_dataset(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    data = [{"title": "A", "ingredients": ["x"], "instructions": ["do a"]},
            {"title": "B", "ingredients": ["y"], "instructions": ["do b"]}]
    p = tmp_path / "ds.json"
    p.write_text(json.dumps(data))
    n = recipe_import.import_dataset(str(p))
    assert n == 2 and recipes.count() == 2


# --- import_site guardrails (robots + cap) --------------------------------

def test_import_site_respects_robots_and_cap(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    urls = [f"http://x/r{i}" for i in range(5)]
    monkeypatch.setattr(recipe_import, "_discover_urls", lambda base: urls)
    monkeypatch.setattr(recipe_import, "_robots_for", lambda base: "RP")
    # disallow r0, allow the rest
    monkeypatch.setattr(recipe_import, "_allowed", lambda rp, url: url != "http://x/r0")
    monkeypatch.setattr(recipe_import.time, "sleep", lambda s: None)
    monkeypatch.setattr(recipe_import, "import_url", lambda url: True)
    result = recipe_import.import_site("http://x", max_recipes=2)
    assert result["added"] == 2                  # capped
    assert result["skipped_robots"] == 1         # r0 blocked
    assert result["considered"] == 5

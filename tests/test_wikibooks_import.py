"""Tests for the Wikibooks Cookbook importer (CC-BY-SA, via the MediaWiki API).
Parser tests use real page structures; the network layer is mocked."""
import pytest

from john_whisk import recipe_import, recipes


class _Resp:
    def __init__(self, payload, status=200, headers=None):
        self.status_code = status
        self.headers = headers or {}
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


# --- API robustness (a bulk job must survive transient throttling) --------

def test_wiki_api_retries_transient_errors(monkeypatch):
    calls = {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] < 3:
            raise recipe_import.requests.RequestException("throttled")
        return _Resp({"query": {"ok": True}})

    monkeypatch.setattr(recipe_import.requests, "get", flaky)
    monkeypatch.setattr(recipe_import.time, "sleep", lambda *_: None)
    assert recipe_import._wiki_api({"action": "query"}) == {"query": {"ok": True}}
    assert calls["n"] == 3          # retried past the two failures


def test_wiki_api_retries_on_429_throttle(monkeypatch):
    seq = [_Resp({}, status=429, headers={"Retry-After": "0"}),
           _Resp({"query": {"ok": True}})]
    monkeypatch.setattr(recipe_import.requests, "get", lambda *a, **k: seq.pop(0))
    monkeypatch.setattr(recipe_import.time, "sleep", lambda *_: None)
    assert recipe_import._wiki_api({"action": "query"}) == {"query": {"ok": True}}


def test_wiki_api_raises_on_error_key(monkeypatch):
    # An API "error" payload (e.g. maxlag/ratelimited) must NOT look like success.
    monkeypatch.setattr(recipe_import.requests, "get",
                        lambda *a, **k: _Resp({"error": {"code": "maxlag"}}))
    monkeypatch.setattr(recipe_import.time, "sleep", lambda *_: None)
    with pytest.raises(recipe_import.requests.RequestException):
        recipe_import._wiki_api({"action": "query"}, _tries=2)


# --- wikitext cleaning ----------------------------------------------------

def test_clean_wikitext_strips_links_and_markup():
    out = recipe_import._clean_wikitext(
        "[[Cookbook:Rice|rice]] and [[Cookbook:Boiling]] '''water''' {{temp}}")
    assert out == "rice and Boiling water"


# --- recipe page parsing --------------------------------------------------

KOSHARI = """{{recipe summary}}
'''Koshari''' is an Egyptian dish.

== Ingredients ==
* 1 [[Cookbook:Cup|cup]] uncooked [[Cookbook:Rice|rice]]
* 1 cup dried [[Cookbook:Lentil|lentils]]
* [[Cookbook:Salt|Salt]] to taste

== Equipment ==
* [[Cookbook:Saucepan|Saucepan]]

== Procedure ==
# Cook the [[Cookbook:Rice|rice]] according to package instructions.
# Cook the lentils in [[Cookbook:Boiling|boiling]] water.
# Combine and serve.

[[Category:Egyptian recipes]]
"""

BASBOUSA = """== Ingredients ==
=== Cake ===
* 1 cup fine [[Cookbook:Semolina|semolina]]
* ½ cup [[Cookbook:Coconut|coconut]]
=== Syrup ===
* 1 cup water
* 1 cup sugar

== Procedure ==
# Preheat the oven to 180°C.
# Combine the semolina and coconut.
"""

NON_RECIPE = """'''Rice''' is a cereal grain.
== Description ==
Rice is widely eaten around the world.
"""


def test_parse_basic_recipe():
    rec = recipe_import.parse_wikibook_recipe(KOSHARI, "Cookbook:Koshari")
    assert rec["title"] == "Koshari"
    assert rec["ingredients"] == "1 cup uncooked rice, 1 cup dried lentils, Salt to taste"
    assert rec["steps"] == [
        "Cook the rice according to package instructions.",
        "Cook the lentils in boiling water.",
        "Combine and serve.",
    ]


def test_parse_ingredient_subsections_are_collected():
    rec = recipe_import.parse_wikibook_recipe(BASBOUSA, "Cookbook:Basbousa")
    # Ingredients from BOTH === Cake === and === Syrup === subsections
    assert rec["ingredients"] == "1 cup fine semolina, ½ cup coconut, 1 cup water, 1 cup sugar"
    assert len(rec["steps"]) == 2


def test_parse_non_recipe_returns_none():
    assert recipe_import.parse_wikibook_recipe(NON_RECIPE, "Cookbook:Rice") is None


# Real Wikibooks bread pages put ingredients in a wikitable (multi-line cells),
# not "*" bullets — the first cell of each data row is the ingredient name.
TABLE_RECIPE = """==Ingredients==
{|
!Ingredient
!Volume
|-
|[[Cookbook:Flour|flour]]
|3 cups
|-
|[[Cookbook:Salt|salt]]
|1 tsp
|}

==Procedure==
# Mix and knead.
# Bake.
"""

# Some pages mislabel the ingredient section ("Procedures") — bullets there are
# really ingredients; the real steps are under the "Procedure" heading.
MISLABELED_RECIPE = """== Procedures ==
* 3 overripe [[Cookbook:Banana|bananas]]
* 1 cup [[Cookbook:Sugar|sugar]]

== Procedure ==
# Mash the bananas.
# Bake at 350F.
"""


def test_parse_table_ingredients():
    rec = recipe_import.parse_wikibook_recipe(TABLE_RECIPE, "Cookbook:Bread")
    assert rec["ingredients"] == "flour, salt"
    assert len(rec["steps"]) == 2


def test_parse_ingredients_under_mislabeled_section():
    rec = recipe_import.parse_wikibook_recipe(MISLABELED_RECIPE, "Cookbook:Banana Bread")
    assert rec["ingredients"] == "3 overripe bananas, 1 cup sugar"
    assert len(rec["steps"]) == 2


def test_parse_carries_tags_and_source():
    rec = recipe_import.parse_wikibook_recipe(
        KOSHARI, "Cookbook:Koshari", source="src", tags="egyptian")
    assert rec["tags"] == "egyptian"
    assert rec["source"] == "src"


# --- category import (network mocked) -------------------------------------

def test_import_wikibooks_category_adds_recipes(monkeypatch):
    monkeypatch.setattr(recipe_import, "_wikibooks_category_titles",
                        lambda category, cap=None: ["Cookbook:Koshari", "Cookbook:Basbousa"])
    monkeypatch.setattr(recipe_import, "_fetch_wikitext_batch",
                        lambda titles: {"Cookbook:Koshari": KOSHARI, "Cookbook:Basbousa": BASBOUSA})
    monkeypatch.setattr(recipe_import.time, "sleep", lambda *_: None)

    added = recipe_import.import_wikibooks_category("Egyptian recipes", tags="egyptian")

    assert added == 2
    assert recipes.count() == 2
    assert recipes.find("Koshari") is not None


def test_import_skips_non_recipe_pages(monkeypatch):
    monkeypatch.setattr(recipe_import, "_wikibooks_category_titles",
                        lambda category, cap=None: ["Cookbook:Rice", "Cookbook:Koshari"])
    monkeypatch.setattr(recipe_import, "_fetch_wikitext_batch",
                        lambda titles: {"Cookbook:Rice": NON_RECIPE, "Cookbook:Koshari": KOSHARI})
    monkeypatch.setattr(recipe_import.time, "sleep", lambda *_: None)

    added = recipe_import.import_wikibooks_category("Recipes")

    assert added == 1          # the non-recipe "Rice" page is dropped
    assert recipes.count() == 1

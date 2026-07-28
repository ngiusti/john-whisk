from john_whisk import main
from john_whisk.cooking import Kitchen


def test_in_recipe_delegates_to_kitchen(monkeypatch):
    k = Kitchen()
    monkeypatch.setattr(k, "current", object())          # make it active
    monkeypatch.setattr(k, "navigate", lambda t: "step 2 of 5")
    assert main.process_utterance("next", k) == "step 2 of 5"


def test_recipes_query_returns_summary(monkeypatch):
    k = Kitchen()
    monkeypatch.setattr(k, "summary", lambda: "You're making omelette right now.")
    # works even when idle, before any routing
    assert main.process_utterance("what am I making right now", k) == \
        "You're making omelette right now."


def test_cook_intent_begins(monkeypatch):
    k = Kitchen()
    monkeypatch.setattr(main.router, "classify", lambda t: "cook")
    monkeypatch.setattr(main.cooking, "dish_from_text", lambda t: "omelette")
    monkeypatch.setattr(k, "begin", lambda dish: f"Okay, making {dish}.")
    assert main.process_utterance("let's make an omelette", k) == "Okay, making omelette."


def test_general_intent_when_idle(monkeypatch):
    k = Kitchen()
    monkeypatch.setattr(main.router, "classify", lambda t: "general")
    monkeypatch.setattr(main.inventory, "ask_general", lambda t: "About six minutes.")
    assert main.process_utterance("how long to boil an egg", k) == "About six minutes."
    assert not k.active


def test_remove_intent_when_idle(monkeypatch):
    k = Kitchen()
    monkeypatch.setattr(main.router, "classify", lambda t: "remove")
    monkeypatch.setattr(main.inventory, "remove_from_text", lambda t: "Took milk off your list.")
    assert main.process_utterance("we're out of milk", k) == "Took milk off your list."

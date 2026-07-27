from john_whisk import main


def test_in_recipe_delegates_to_navigate(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(main.cooking, "navigate", lambda s, t: ("step 2 of 5", sentinel))
    reply, session = main.process_utterance("next", "ACTIVE_SESSION")
    assert reply == "step 2 of 5"
    assert session is sentinel


def test_cook_intent_starts_session(monkeypatch):
    made = object()
    monkeypatch.setattr(main.router, "classify", lambda t: "cook")
    monkeypatch.setattr(main.cooking, "dish_from_text", lambda t: "omelette")
    monkeypatch.setattr(main.cooking, "start", lambda dish: (made, "Okay, making omelette."))
    reply, session = main.process_utterance("let's make an omelette", None)
    assert session is made
    assert reply == "Okay, making omelette."


def test_general_intent_leaves_session_none(monkeypatch):
    monkeypatch.setattr(main.router, "classify", lambda t: "general")
    monkeypatch.setattr(main.llm, "ask", lambda t: "About six minutes.")
    reply, session = main.process_utterance("how long to boil an egg", None)
    assert reply == "About six minutes."
    assert session is None


def test_remove_intent_routes_and_keeps_session_none(monkeypatch):
    monkeypatch.setattr(main.router, "classify", lambda t: "remove")
    monkeypatch.setattr(main.inventory, "remove_from_text", lambda t: "Took milk off your list.")
    reply, session = main.process_utterance("we're out of milk", None)
    assert reply == "Took milk off your list."
    assert session is None

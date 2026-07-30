"""Conversational domain 'mode' (calendar). Network/Google mocked; DB isolated."""
from john_whisk import config, mode, mealplan, main, cooking


def _iso(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "p.db"))
    monkeypatch.setattr(config, "RECIPES_DB_PATH", str(tmp_path / "r.db"))


def test_detect_set_and_exit():
    assert mode.detect_set("let's look into the calendar") == "calendar"
    assert mode.detect_set("switch to calendar") == "calendar"
    assert mode.detect_set("what's for dinner") is None
    assert mode.is_exit("never mind")
    assert not mode.is_exit("add eggs")


def test_enter_calendar_mode(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    k = cooking.Kitchen()
    r = main.process_utterance("let's look into the calendar", k)
    assert "calendar mode" in r.lower()
    assert mode.get() == "calendar"


def test_calendar_mode_biases_ambiguous(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from john_whisk import calwrite
    monkeypatch.setattr(calwrite, "available", lambda: False)   # local fallback, no network
    k = cooking.Kitchen()
    main.process_utterance("calendar mode", k)
    # in calendar mode this goes through the calendar path (confirm-first)
    ask = main.process_utterance("add a dentist appointment tomorrow at 4pm", k)
    assert "should i" in ask.lower() and "dentist" in ask.lower()
    done = main.process_utterance("yes", k)          # confirm -> saved (local fallback)
    assert "saved" in done.lower()
    assert mode.get() == "calendar"                  # still in mode


def test_calendar_mode_reads_questions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    k = cooking.Kitchen()
    mode.set("calendar")
    r = main.process_utterance("anything going on this week", k)
    assert "coming up" in r.lower() or "nothing on the calendar" in r.lower()


def test_calendar_mode_exits_on_strong_command(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    k = cooking.Kitchen()
    mode.set("calendar")
    r = main.process_utterance("how many recipes do you have", k)
    assert mode.get() is None                # a clear food command exits the mode
    assert "recipe" in r.lower()


def test_exit_phrase_clears_mode(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    k = cooking.Kitchen()
    mode.set("calendar")
    r = main.process_utterance("never mind", k)
    assert mode.get() is None and "back to" in r.lower()

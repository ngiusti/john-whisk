from john_whisk import llm


def test_ask_returns_nonempty_text():
    reply = llm.ask("In one short sentence, what can I cook with eggs?")
    assert isinstance(reply, str)
    assert len(reply.strip()) > 0


def test_ask_handles_empty_input():
    assert llm.ask("") == ""

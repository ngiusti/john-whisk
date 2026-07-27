from john_whisk import router


def test_suggest():
    assert router.classify("What can I make for dinner?") == "suggest"


def test_add():
    assert router.classify("I bought chicken and some eggs") == "add"


def test_general():
    assert router.classify("How long should I boil an egg?") == "general"


def test_precedence_suggest_beats_add():
    assert router.classify("what can i make with the chicken i bought") == "suggest"


def test_list_query():
    assert router.classify("What do I have?") == "list"


def test_have_question_not_routed_to_add():
    # "do I have" is a query, must NOT be treated as an add command
    assert router.classify("what do I have left") == "list"


def test_volume():
    assert router.classify("set volume to 40 percent") == "volume"

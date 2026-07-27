from john_whisk import router


def test_suggest():
    assert router.classify("What can I make for dinner?") == "suggest"


def test_add():
    assert router.classify("I bought chicken and some eggs") == "add"


def test_general():
    assert router.classify("How long should I boil an egg?") == "general"


def test_precedence_suggest_beats_add():
    assert router.classify("what can i make with the chicken i bought") == "suggest"

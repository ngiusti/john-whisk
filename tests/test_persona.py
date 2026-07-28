from john_whisk import persona


def test_line_returns_nonempty_for_each_moment():
    for moment in ("startup", "ack", "signoff", "error", "miss"):
        s = persona.line(moment)
        assert isinstance(s, str) and s.strip()


def test_line_from_the_moments_set():
    assert persona.line("ack") in persona.LINES["ack"]


def test_unknown_moment_safe_default():
    # an unknown moment must not crash; returns a usable string
    s = persona.line("does-not-exist")
    assert isinstance(s, str) and s.strip()


def test_lines_are_short_and_plain():
    for moment, lines in persona.LINES.items():
        for s in lines:
            assert 0 < len(s) <= 120          # spoken-length
            assert "{" not in s and "}" not in s   # no unfilled templates

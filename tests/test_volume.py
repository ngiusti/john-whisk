from john_whisk import volume


def test_parse_digits():
    assert volume.parse_percent("set volume to 40 percent") == 40


def test_parse_words():
    assert volume.parse_percent("set the volume to fifty percent") == 50


def test_parse_clamps_high():
    assert volume.parse_percent("set volume to 300") == 100


def test_parse_none_when_no_number():
    assert volume.parse_percent("turn up the music") is None


def test_set_from_text_confirms(monkeypatch):
    monkeypatch.setattr(volume.subprocess, "run", lambda *a, **k: None)
    assert volume.set_from_text("set volume to 40 percent") == "Volume set to 40 percent."


def test_set_from_text_no_number(monkeypatch):
    monkeypatch.setattr(volume.subprocess, "run", lambda *a, **k: None)
    assert "didn't catch" in volume.set_from_text("set the volume").lower()

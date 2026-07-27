from remy import stt


def test_transcribe_known_phrase(spoken_wav):
    text = stt.transcribe(spoken_wav).lower()
    assert "testing" in text or "one" in text

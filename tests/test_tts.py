import wave
from john_whisk import tts


def test_synthesize_produces_valid_wav(tmp_path):
    out = str(tmp_path / "out.wav")
    path = tts.synthesize("Hello from John Whisk.", out)
    assert path == out
    with wave.open(out, "rb") as w:
        assert w.getnframes() > 0

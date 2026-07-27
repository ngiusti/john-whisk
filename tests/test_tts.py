import wave
from remy import tts


def test_synthesize_produces_valid_wav(tmp_path):
    out = str(tmp_path / "out.wav")
    path = tts.synthesize("Hello from Remy.", out)
    assert path == out
    with wave.open(out, "rb") as w:
        assert w.getnframes() > 0

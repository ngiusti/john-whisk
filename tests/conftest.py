import subprocess
import os
import pytest
from remy import config


@pytest.fixture(scope="session")
def spoken_wav(tmp_path_factory):
    """A 16kHz mono WAV of a known phrase, made with Piper + ffmpeg (no mic)."""
    d = tmp_path_factory.mktemp("audio")
    raw = os.path.join(d, "piper.wav")
    out = os.path.join(d, "spoken16k.wav")
    subprocess.run(
        [config.PIPER_BIN, "--model", config.PIPER_VOICE, "--output_file", raw],
        input=b"testing one two three", cwd=config.PIPER_DIR, check=True,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-i", raw, "-ar", "16000", "-ac", "1", out],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return out

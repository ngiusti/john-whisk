import subprocess
import os
import pytest
from john_whisk import config


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


@pytest.fixture(autouse=True)
def _isolate_recipes_db(tmp_path, monkeypatch):
    """Point the recipe store at a fresh empty temp DB for every test, so
    cooking.start lookups meant to hit the mocked LLM don't accidentally match
    the seeded on-device library. Tests that need recipe content monkeypatch
    RECIPES_DB_PATH themselves (that override runs after this and wins).
    DB_PATH is intentionally left alone (test_config checks its real value;
    inventory tests set it themselves)."""
    monkeypatch.setattr(config, "RECIPES_DB_PATH", str(tmp_path / "recipes.db"), raising=False)
    from john_whisk import mode
    mode.clear()          # module-global conversational mode; start each test clean

import subprocess
from remy import config


def synthesize(text: str, out_path: str = None) -> str:
    """Render text to a WAV file with Piper. Returns the WAV path."""
    out_path = out_path or config.OUT_WAV
    subprocess.run(
        [config.PIPER_BIN, "--model", config.PIPER_VOICE, "--output_file", out_path],
        input=text.encode("utf-8"), cwd=config.PIPER_DIR, check=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return out_path


def speak(text: str) -> None:
    """Synthesize text and play it through the speaker."""
    if not text or not text.strip():
        return
    from remy import audio          # lazy import: keeps this module usable before Task 6
    path = synthesize(text)
    audio.play_wav(path)

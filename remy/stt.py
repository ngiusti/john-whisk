import subprocess
from remy import config


def transcribe(wav_path: str) -> str:
    """Transcribe a 16kHz mono WAV to text using whisper.cpp. Returns '' on failure."""
    try:
        result = subprocess.run(
            [config.WHISPER_BIN, "-m", config.WHISPER_MODEL,
             "-f", wav_path, "-nt", "-t", str(config.WHISPER_THREADS)],
            capture_output=True, text=True, timeout=60,
        )
    except (subprocess.SubprocessError, OSError):
        return ""
    return result.stdout.strip()
